"""Basic model templates for Anki deck generation."""

DEFAULT_MODEL_TEMPLATES_YAML = """
main:
  - name: "Card 1"
    qfmt: "{{Front}}<br>{{Image}}"
    afmt: "{{FrontSide}}<hr id=answer>{{Back}}<br><br>{{Example}}{{Audio}}<br><br><i>{{Notes}}</i>"
css: |
  .card {
    font-family: arial;
    font-size: 20px;
    text-align: center;
    color: black;
    background-color: white;
  }
"""
