import functools
from flask import Flask, jsonify, request, abort,Response, make_response, render_template_string
from sqlalchemy import func, or_
from werkzeug.exceptions import HTTPException
import csv
from io import StringIO

from weasyprint import HTML

app = Flask(__name__)
app.config.from_object("config.Config")

from models import HadithCollection, Book, Chapter, Hadith


@app.before_request
def verify_secret():
    if not app.debug and request.headers.get("x-aws-secret") != app.config["AWS_SECRET"]:
        abort(401)


@app.errorhandler(HTTPException)
def jsonify_http_error(error):
    response = {"error": {"details": error.description, "code": error.code}}

    return jsonify(response), error.code


def paginate_results(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        limit = int(request.args.get("limit", 50))
        page = int(request.args.get("page", 1))

        queryset = f(*args, **kwargs).paginate(page=page, per_page=limit, max_per_page=100)
        result = {
            "data": [x.serialize() for x in queryset.items],
            "total": queryset.total,
            "limit": queryset.per_page,
            "previous": queryset.prev_num,
            "next": queryset.next_num,
        }
        return jsonify(result)

    return decorated_function


def single_resource(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        result = f(*args, **kwargs).first_or_404()
        result = result.serialize()
        return jsonify(result)

    return decorated_function


@app.route("/", methods=["GET"])
def home():
    return "<h1>Welcome to sunnah.com API.</h1>"


@app.route("/v1/collections", methods=["GET"])
@paginate_results
def api_collections():
    return HadithCollection.query.order_by(HadithCollection.collectionID)


@app.route("/v1/collections/<string:name>", methods=["GET"])
@single_resource
def api_collection(name):
    return HadithCollection.query.filter_by(name=name)


@app.route("/v1/collections/<string:name>/books", methods=["GET"])
@paginate_results
def api_collection_books(name):
    return Book.query.filter_by(collection=name, status=4).order_by(func.abs(Book.ourBookID))


@app.route("/v1/collections/<string:name>/books/<string:bookNumber>", methods=["GET"])
@single_resource
def api_collection_book(name, bookNumber):
    book_id = Book.get_id_from_number(bookNumber)
    return Book.query.filter_by(collection=name, status=4, ourBookID=book_id)


@app.route("/v1/collections/<string:collection_name>/books/<string:bookNumber>/hadiths", methods=["GET"])
@paginate_results
def api_collection_book_hadiths(collection_name, bookNumber):
    return Hadith.query.filter_by(collection=collection_name, bookNumber=bookNumber).order_by(Hadith.englishURN)


@app.route("/v1/collections/<string:collection_name>/hadiths/<string:hadithNumber>", methods=["GET"])
@single_resource
def api_collection_hadith(collection_name, hadithNumber):
    return Hadith.query.filter_by(collection=collection_name, hadithNumber=hadithNumber)


@app.route("/v1/collections/<string:collection_name>/books/<string:bookNumber>/chapters", methods=["GET"])
@paginate_results
def api_collection_book_chapters(collection_name, bookNumber):
    book_id = Book.get_id_from_number(bookNumber)
    return Chapter.query.filter_by(collection=collection_name, arabicBookID=book_id).order_by(Chapter.babID)


@app.route("/v1/collections/<string:collection_name>/books/<string:bookNumber>/chapters/<float:chapterId>", methods=["GET"])
@single_resource
def api_collection_book_chapter(collection_name, bookNumber, chapterId):
    book_id = Book.get_id_from_number(bookNumber)
    return Chapter.query.filter_by(collection=collection_name, arabicBookID=book_id, babID=chapterId)


@app.route("/v1/hadiths/<int:urn>", methods=["GET"])
@single_resource
def api_hadith(urn):
    return Hadith.query.filter(or_(Hadith.arabicURN == urn, Hadith.englishURN == urn))


@app.route("/v1/hadiths/random", methods=["GET"])
@single_resource
def api_hadiths_random():
    # TODO Make this configurable instead of hardcoding
    return Hadith.query.filter_by(collection="riyadussalihin").order_by(func.rand())



#CSV EXPORT 
@app.route("/v1/collections/export/csv", methods=["GET"])
def export_collections_csv():
    collections = HadithCollection.query.all()
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(["Collection ID", "Name", "Description"])
    for collection in collections:
        writer.writerow([collection.collectionID, collection.name, collection.description])
    
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=collections.csv"
    output.headers["Content-Type"] = "text/csv"
    return output

#PDF export
@app.route("/v1/collections/export/pdf", methods=["GET"])
def export_collections_pdf():
    collections = HadithCollection.query.all()
    html_content = render_template_string(
        """
        <!DOCTYPE html>
        <html>
        <head><title>Collections</title></head>
        <body>
        <h1>Hadith Collections</h1>
        <ul>
            {% for collection in collections %}
                <li>{{ collection.name }}: {{ collection.description }}</li>
            {% endfor %}
        </ul>
        </body>
        </html>
        """, collections=collections
    )
    pdf = HTML(string=html_content).write_pdf()
    response = make_response(pdf)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = "inline; filename=collections.pdf"
    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0")
