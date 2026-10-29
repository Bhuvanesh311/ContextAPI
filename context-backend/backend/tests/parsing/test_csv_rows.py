from app.knowledge.parsing.parsers.structured.csv_parser import CSVParser


def test_rows_become_labelled_lines():
    rows = [
        {"sku": "A100", "item": "steel bolts", "stock": "5400"},
        {"sku": "A200", "item": "copper\n wire", "stock": ""},
    ]
    assert CSVParser._normalize_content(rows) == (
        "sku: A100 | item: steel bolts | stock: 5400\n"
        "sku: A200 | item: copper wire | stock: "
    )
