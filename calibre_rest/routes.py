import json
import tempfile
from os import path

from flask import abort
from flask import current_app as app
from flask import jsonify, make_response, request
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

from calibre_rest import __version__
from calibre_rest.errors import (
    CalibreRuntimeError,
    ExistingItemError,
    InvalidPayloadError,
)
from calibre_rest.models import Book

calibredb = app.config["CALIBRE_WRAPPER"]


@app.route("/health")
def version():
    return response(
        200,
        jsonify(calibre_version=calibredb.version(), calibre_rest_version=__version__),
    )


@app.route("/books/<int:id>")
def get_book(id):
    book = calibredb.get_book(id)
    if not book:
        abort(404, f"book {id} does not exist")

    return response(200, jsonify(books=book))


# TODO list with sort, filter search, pagination
@app.route("/books")
def get_books():
    """Get list of books.

    Query Parameters:
    limit: Maximum number of results in a page
    before_id: Results before id
    after_id: Results after id
    sort: Sort results by field
    search: Search results
    """

    per_page = request.args.get("per_page")

    if per_page:
        books = calibredb.get_books(limit=int(per_page))
    else:
        books = calibredb.get_books()

    if not len(books):
        return response(204, jsonify(books=[]))

    return response(200, jsonify(books=books))


# TODO add multiple and with directory
@app.route("/books", methods=["POST"])
def add_book():
    """Add book to calibre library with book file and optional data."""

    if "multipart/form-data" not in request.content_type:
        abort(415, "Only multipart/form-data allowed")

    if "file" not in request.files:
        raise InvalidPayloadError("No file provided")

    file = request.files["file"]
    if file and file.filename == "":
        raise InvalidPayloadError("Invalid file or filename")

    if not allowed_file(file.filename):
        raise InvalidPayloadError(f"Invalid filename ({file.filename})")

    # save file to a temporary location for upload
    tempdir = tempfile.gettempdir()
    tempfilepath = path.join(tempdir, secure_filename(file.filename))
    file.save(tempfilepath)

    if not path.isfile(tempfilepath):
        raise FileNotFoundError(f"{tempfilepath} not found.")

    book = Book()

    # Check if optional input data exists in form field "data".
    # If exists, check for "automerge" key to modify automerge behaviour.
    # If any book field keys are present, add them to the book dict.

    json_data = request.form.get("data")
    validate(json_data, Book)
    automerge = "ignore"

    if json_data is not None:
        data = json.loads(json_data)
        automerge = data.pop("automerge", "ignore")
        if len(data):
            book = Book(**data)

    id = calibredb.add_one(tempfilepath, book, automerge)
    return response(201, jsonify(id=id))


@app.route("/books/empty", methods=["POST"])
def add_empty_book():
    """Add empty book to calibre library with optional data."""

    if request.content_type != "application/json":
        abort(415, "Only application/json allowed")

    book = Book()
    if request.data != bytes():
        validate(request.data, Book)
        book = request.get_json()
        book = Book(**book)

    id = calibredb.add_one_empty(book)
    return response(201, jsonify(id=id))


@app.route("/books/<int:id>", methods=["PUT"])
def update_book(id):
    """Update existing book in calibre library with JSON data."""

    if request.content_type != "application/json":
        abort(415, "Only application/json allowed")

    if request.get_json() == {}:
        abort(400)

    validate(request.data, Book)
    book = request.get_json()
    book = Book(**book)
    returned_id = calibredb.set_metadata(id, book, None)

    if returned_id == -1:
        abort(404, f"book {id} does not exist")

    book = calibredb.get_book(returned_id)
    return response(200, jsonify(books=book))


@app.route("/books/<int:id>", methods=["DELETE"])
def delete_book(id):
    """Remove existing book in calibre library."""
    calibredb.remove([id])

    # check if book still exists
    book = calibredb.get_book(id)
    if book:
        abort(500, f"book {id} was not deleted")

    return response(200, "")


# export
@app.route("/export/<int:id>")
def export_book(id):
    pass


# export --all
@app.route("/export")
def export_books():
    pass


@app.errorhandler(HTTPException)
def handle_http_error(e):
    return jsonify(error=str(e)), e.code


@app.errorhandler(ExistingItemError)
def handle_existing_item_error(e):
    return jsonify(error=str(e)), 409


@app.errorhandler(json.JSONDecodeError)
def handle_json_decode_error(e):
    return jsonify(error=f"Error decoding JSON: {str(e)}"), 500


@app.errorhandler(TimeoutError)
def handle_timeout_error(e):
    return jsonify(error=str(e)), 500


@app.errorhandler(ValueError)
def handle_value_error(e):
    return jsonify(error=str(e)), 400


@app.errorhandler(CalibreRuntimeError)
def handle_calibre_runtime_error(e):
    return jsonify(error=str(e)), 500


def response(status_code, data, headers={"Content-Type": "application/json"}):
    response = make_response(data, status_code)

    for k, v in headers.items():
        response.headers[k] = v

    return response


def validate(data: str, cls):
    """Validate JSON string with Book.

    Args:
    data (str): JSON string.

    Raises:
    HTTPException: 400 error code when validation fails
    """
    if data is None or data == bytes():
        app.logger.warning("No input data provided")
        return

    json_data = json.loads(data)
    errors = cls.validate(json_data)
    if len(errors):
        data = {"errors": []}
        for e in errors:
            if len(e.path):
                data["errors"].append({e.path.popleft(): e.message})
            else:
                data["errors"].append({"key": e.message})
        abort(response(400, jsonify(data)))


def allowed_file(filename: str) -> bool:
    if filename.startswith("-"):
        return False
    return filename.lower().endswith(calibredb.ALLOWED_FILE_EXTENSIONS)
