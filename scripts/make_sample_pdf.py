"""Regenerate sample_docs/expense_policy.pdf. One-off helper; needs `pip install fpdf2`."""

from pathlib import Path

from fpdf import FPDF

PAGES = [
    (
        "Lumenfold Systems Expense Policy: Travel",
        [
            "Flights under 6 hours must be booked in economy class. Business class is permitted on "
            "flights longer than 6 hours with written approval from a vice president.",
            "The hotel cap is 180 euros per night. In London and Zurich the hotel cap is 240 euros per night.",
            "The meal per diem while travelling is 55 euros per day. Alcohol is not reimbursed.",
            "Rail travel should be preferred over flying for journeys under 4 hours.",
        ],
    ),
    (
        "Lumenfold Systems Expense Policy: Reimbursement",
        [
            "Expense claims must be submitted within 45 days of the expense date. Claims submitted later are rejected.",
            "A receipt is required for any expense over 25 euros.",
            "Approved claims are paid within 10 business days.",
            "The company card has a spending limit of 5,000 euros per month.",
            "Employees receive a one-off home office allowance of 350 euros when they join.",
        ],
    ),
]


def main() -> None:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    for title, paragraphs in PAGES:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 16)
        pdf.multi_cell(0, 10, title)
        pdf.ln(4)
        pdf.set_font("Helvetica", "", 12)
        for paragraph in paragraphs:
            pdf.multi_cell(0, 7, paragraph)
            pdf.ln(3)
    target = Path(__file__).resolve().parent.parent / "sample_docs" / "expense_policy.pdf"
    pdf.output(str(target))
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
