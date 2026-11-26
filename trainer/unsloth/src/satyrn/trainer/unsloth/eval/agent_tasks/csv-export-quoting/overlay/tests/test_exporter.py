from exporter import to_csv, to_tsv


def test_header_and_rows():
    rows = [{"invoice": "A1", "customer": "Ann", "amount": 5, "note": None}]
    assert to_csv(rows) == "invoice,customer,amount,note\nA1,Ann,5,\n"


def test_lines_end_with_a_bare_newline():
    assert "\r" not in to_csv([{"invoice": "A1", "note": "ok"}])


def test_tsv_fields_are_written_exactly():
    rows = [{"invoice": "A2", "customer": "Bob", "amount": 7, "note": 'late, "again"'}]
    assert to_tsv(rows) == 'invoice\tcustomer\tamount\tnote\nA2\tBob\t7\tlate, "again"\n'


def test_commas_are_quoted():
    rows = [{"invoice": "A2", "customer": "Bob", "amount": 7, "note": "late, again"}]
    assert to_csv(rows) == 'invoice,customer,amount,note\nA2,Bob,7,"late, again"\n'


def test_quotes_are_doubled():
    rows = [{"invoice": "A3", "customer": "Cy", "amount": 1, "note": 'said "hi"'}]
    assert to_csv(rows).splitlines()[1] == 'A3,Cy,1,"said ""hi"""'


def test_line_breaks_inside_a_field_are_quoted():
    rows = [{"invoice": "A4", "customer": "Di", "amount": 2, "note": "two\nlines"}]
    assert to_csv(rows) == 'invoice,customer,amount,note\nA4,Di,2,"two\nlines"\n'
