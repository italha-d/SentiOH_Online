from bs4 import BeautifulSoup

from integrations.fsai_scraper.fsai_recall_scraper import table_to_rows


def soup(html):
    return BeautifulSoup(html, "html.parser")


def test_alert_summary_is_not_parsed_as_products():
    html = """
    <table>
      <tr><td>Alert Notification:</td><td>2026.53</td></tr>
      <tr><td>Product Identification:</td><td>Macroom Buffalo Cheese</td></tr>
      <tr><td>Batch Code</td><td>Use-by date: 07/09/2026</td></tr>
      <tr><td>Country Of Origin:</td><td>Ireland</td></tr>
    </table>
    """
    assert table_to_rows(soup(html), "", "") == []


def test_rowspan_product_and_pack_are_propagated_to_batch_rows():
    html = """
    <table>
      <tr>
        <th>Product Name</th><th>Pack Size</th><th>Batch Code</th><th>Best Before</th>
      </tr>
      <tr>
        <td rowspan="2">Tesco Sesame Seeds</td>
        <td rowspan="2">100g</td>
        <td>155 N01</td><td>May 2027</td>
      </tr>
      <tr>
        <td>203 N01</td><td>June 2027</td>
      </tr>
    </table>
    """
    rows = table_to_rows(soup(html), "", "")
    assert rows == [
        {
            "Product Name": "Tesco Sesame Seeds",
            "Brand": "",
            "Pack Size": "100g",
            "Batch Code": "155 N01",
            "Use By": "",
            "Best Before": "May 2027",
        },
        {
            "Product Name": "Tesco Sesame Seeds",
            "Brand": "",
            "Pack Size": "100g",
            "Batch Code": "203 N01",
            "Use By": "",
            "Best Before": "June 2027",
        },
    ]


def test_rowspan_shared_use_by_is_applied_to_all_products():
    html = """
    <table>
      <tr><th>Product Name</th><th>Pack Size</th><th>Use-by date</th></tr>
      <tr><td>Product A</td><td>4 x 60g</td><td rowspan="3">28.05.2026</td></tr>
      <tr><td>Product B</td><td>4 x 60g</td></tr>
      <tr><td>Product C</td><td>4 x 60g</td></tr>
    </table>
    """
    rows = table_to_rows(soup(html), "", "")
    assert [r["Use By"] for r in rows] == [
        "28.05.2026", "28.05.2026", "28.05.2026"
    ]
    assert [r["Product Name"] for r in rows] == [
        "Product A", "Product B", "Product C"
    ]


def test_retailer_group_heading_is_not_a_product():
    html = """
    <table>
      <tr><th>Product Name</th><th>Pack Size</th><th>Batch Code</th></tr>
      <tr><td colspan="3">Aldi</td></tr>
      <tr><td>Real Chicken Product</td><td>500g</td><td>26124-640</td></tr>
    </table>
    """
    rows = table_to_rows(soup(html), "", "")
    assert len(rows) == 1
    assert rows[0]["Product Name"] == "Real Chicken Product"


def test_country_and_batch_labels_never_become_products():
    html = """
    <table>
      <tr><th>Product Name</th><th>Pack Size</th><th>Batch Code</th></tr>
      <tr><td>Country Of Origin:</td><td>Ireland</td><td></td></tr>
      <tr><td>Batch Code</td><td>Use-by date: 07/09/2026</td><td></td></tr>
    </table>
    """
    assert table_to_rows(soup(html), "", "") == []
