"""Generate realistic sample Word and Excel documents for Cognify live demonstration.

Creates:
- data/downloads/company_policy.docx
- data/downloads/sales_2025.xlsx
- data/downloads/sales_2026.xlsx
"""

from pathlib import Path
import docx
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS_DIR = PROJECT_ROOT / "data" / "downloads"


def generate_company_policy_docx(dest: Path) -> None:
    """Generate company_policy.docx with policy sections and benefit tables."""
    doc = docx.Document()
    doc.core_properties.title = "Cognify Global Corporate Policy and Employee Handbook"
    doc.core_properties.author = "Human Resources & Legal Department"

    doc.add_heading("Cognify Corporate Policy & Employee Handbook", level=1)
    doc.add_paragraph(
        "Welcome to Cognify. This document outlines company policies, leave entitlements, "
        "employee benefits, and revenue recognition guidelines."
    )

    # Section 1: Leave Policy
    doc.add_heading("1. Annual Leave and Time-Off Policy", level=2)
    doc.add_paragraph(
        "All full-time employees are eligible for 25 days of paid annual vacation leave per calendar year. "
        "Annual leave accrues on a monthly basis from the official date of joining. "
        "In addition, employees are entitled to 12 days of paid sick leave and 10 standard public holidays."
    )
    doc.add_paragraph(
        "Unused annual leave of up to 10 days may be carried over into the following calendar year, "
        "provided it is utilized before March 31st."
    )

    # Section 2: Employee Benefits
    doc.add_heading("2. Employee Health and Wellness Benefits", level=2)
    doc.add_paragraph(
        "All permanent employees and their designated dependents are eligible for comprehensive medical, "
        "dental, and vision insurance coverage starting on their first day of active employment. "
        "The company covers 100% of the employee premium and 80% of dependent premiums."
    )

    # Benefits Table
    table = doc.add_table(rows=4, cols=3)
    headers = ["Benefit Category", "Coverage Tier", "Annual Maximum"]
    for i, h in enumerate(headers):
        table.cell(0, i).text = h

    rows_data = [
        ["Comprehensive Medical", "Tier 1 (In-Network)", "$1,000,000"],
        ["Dental & Orthodontics", "Comprehensive", "$5,000"],
        ["Wellness & Gym Stipend", "All Employees", "$1,200 ($100/mo)"],
    ]
    for row_idx, row_values in enumerate(rows_data, start=1):
        for col_idx, val in enumerate(row_values):
            table.cell(row_idx, col_idx).text = val

    # Section 3: Revenue Recognition Policy
    doc.add_heading("3. Revenue Recognition & Financial Reporting Policy", level=2)
    doc.add_paragraph(
        "Cognify recognizes revenue in accordance with standard international accounting standards (IFRS 15 / ASC 606). "
        "Revenue from software licensing and enterprise analytics subscriptions is recognized ratably over "
        "the contractual term as performance obligations are satisfied. Consulting and implementation services "
        "are recognized upon delivery and customer sign-off."
    )

    # Section 4: Notice Period & Remote Work
    doc.add_heading("4. Remote Work & Notice Period", level=2)
    doc.add_paragraph(
        "Cognify champions a remote-first workplace culture. Employees may work from any location within "
        "their country of residence with a secure internet connection. Standard resignation notice period is "
        "30 calendar days for individual contributors and 60 days for managerial roles."
    )

    doc.save(str(dest))
    print(f"Generated {dest}")


def generate_sales_spreadsheets(dir_path: Path) -> None:
    """Generate sales_2025.xlsx and sales_2026.xlsx with realistic financial numbers."""
    data_2025 = {
        "Date": [
            "2025-01-15", "2025-02-18", "2025-03-22", "2025-04-10", "2025-05-14",
            "2025-06-20", "2025-07-15", "2025-08-19", "2025-09-25", "2025-10-12",
            "2025-11-18", "2025-12-05", "2025-03-15", "2025-06-11", "2025-09-08",
            "2025-11-20"
        ],
        "Region": [
            "North", "South", "East", "West", "North",
            "South", "East", "West", "North", "South",
            "East", "West", "North", "South", "East",
            "West"
        ],
        "Product": [
            "Cognify Enterprise", "Cognify Cloud", "Cognify Core", "Cognify Cloud", "Cognify Enterprise",
            "Cognify Core", "Cognify Enterprise", "Cognify Cloud", "Cognify Core", "Cognify Enterprise",
            "Cognify Cloud", "Cognify Core", "Cognify Cloud", "Cognify Enterprise", "Cognify Core",
            "Cognify Enterprise"
        ],
        "Revenue": [
            120000.0, 85000.0, 95000.0, 110000.0, 130000.0,
            75000.0, 140000.0, 115000.0, 90000.0, 150000.0,
            105000.0, 80000.0, 98000.0, 145000.0, 88000.0,
            124000.0
        ],
        "Units": [12, 17, 19, 15, 13, 15, 14, 16, 18, 15, 21, 16, 20, 15, 18, 12],
    }

    data_2026 = {
        "Date": [
            "2026-01-14", "2026-02-17", "2026-03-20", "2026-04-12", "2026-05-15",
            "2026-06-19", "2026-07-14", "2026-08-18", "2026-09-22", "2026-10-15",
            "2026-11-19", "2026-12-08", "2026-03-18", "2026-06-14", "2026-09-10",
            "2026-11-22"
        ],
        "Region": [
            "North", "South", "East", "West", "North",
            "South", "East", "West", "North", "South",
            "East", "West", "North", "South", "East",
            "West"
        ],
        "Product": [
            "Cognify Enterprise", "Cognify Cloud", "Cognify Core", "Cognify Cloud", "Cognify Enterprise",
            "Cognify Core", "Cognify Enterprise", "Cognify Cloud", "Cognify Core", "Cognify Enterprise",
            "Cognify Cloud", "Cognify Core", "Cognify Cloud", "Cognify Enterprise", "Cognify Core",
            "Cognify Enterprise"
        ],
        "Revenue": [
            155000.0, 110000.0, 125000.0, 140000.0, 165000.0,
            95000.0, 180000.0, 150000.0, 115000.0, 190000.0,
            135000.0, 105000.0, 125000.0, 185000.0, 112000.0,
            160000.0
        ],
        "Units": [15, 22, 25, 20, 16, 19, 18, 21, 23, 19, 27, 21, 25, 19, 23, 16],
    }

    f1 = dir_path / "sales_2025.xlsx"
    f2 = dir_path / "sales_2026.xlsx"

    with pd.ExcelWriter(str(f1), engine="openpyxl") as writer:
        pd.DataFrame(data_2025).to_excel(writer, sheet_name="Sales", index=False)

    with pd.ExcelWriter(str(f2), engine="openpyxl") as writer:
        pd.DataFrame(data_2026).to_excel(writer, sheet_name="Sales", index=False)

    print(f"Generated {f1}")
    print(f"Generated {f2}")


def main() -> None:
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    generate_company_policy_docx(DOWNLOADS_DIR / "company_policy.docx")
    generate_sales_spreadsheets(DOWNLOADS_DIR)
    print("Sample datasets generated successfully in data/downloads/.")


if __name__ == "__main__":
    main()
