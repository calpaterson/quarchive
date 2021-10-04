import tempfile
import magic


def test_favicon(client):
    ALLOWED_MIMES = ["image/vnd.microsoft.icon", "image/x-icon"]

    response = client.get("/favicon.ico")
    with tempfile.TemporaryFile(mode="w+b") as temp_file:
        temp_file.write(response.data)
        temp_file.seek(0)
        mime = magic.from_buffer(temp_file.read(2048), mime=True)
    assert mime in ALLOWED_MIMES
