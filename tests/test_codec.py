import base64

from ecoledirecte_api.codec import clean, data_of, decode_payload, html_to_text, try_b64


def b64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def test_try_b64_decodes_utf8_text():
    assert try_b64(b64("Bonjour élève")) == "Bonjour élève"


def test_try_b64_rejects_plain_text():
    assert try_b64("Mathématiques") is None
    assert try_b64("1234") is None


def test_html_to_text_keeps_readable_structure():
    assert html_to_text("<p>Un</p><p>Deux<br>Trois</p>") == "Un\n\nDeux\nTrois"


def test_decode_payload_decodes_only_content_keys():
    payload = {
        "contenu": b64("<p>Faire l'exercice 3</p>"),
        "matiere": b64("Français"),
        "nested": [{"resume": b64("<b>Résumé</b>")}],
    }

    decoded = decode_payload(payload)

    assert decoded["contenu"] == "Faire l'exercice 3"
    assert decoded["matiere"] == b64("Français")
    assert decoded["nested"][0]["resume"] == "Résumé"


def test_clean_unwraps_envelope_and_decodes():
    payload = {"code": 200, "data": {"message": b64("<p>Bonjour</p>")}}

    assert clean(payload) == {"message": "Bonjour"}
    assert data_of(payload) == {"message": b64("<p>Bonjour</p>")}


def test_clean_keeps_plain_strings():
    assert clean({"code": 200, "data": {"message": "Mot de passe invalide"}}) == {
        "message": "Mot de passe invalide"
    }
