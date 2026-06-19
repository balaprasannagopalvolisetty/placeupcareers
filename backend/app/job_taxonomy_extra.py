"""Supplementary job taxonomy — fills the remaining roles from the demand-weighted
Top-200 list (Sales, HR, Operations/Supply Chain, Customer Service, Skilled Trades,
Administrative, and extra roles in existing domains).

Merged into job_taxonomy.CATEGORIES so the scraper queries them, the categorizer
tags them, and the Jobs filter sidebar lists them. Visa tags are conservative:
professional/sponsorable roles get OPT/H-1B; predominantly-domestic roles get an
empty tuple (still collected and shown, just not flagged visa-friendly).
"""
from __future__ import annotations

from app.job_taxonomy import Category, Role

EXTRA_CATEGORIES: tuple[Category, ...] = (
    Category("Product & Program Management", "ClipboardList", (
        Role("Project Manager", ("project manager", "technical project manager", "it project manager", "project coordinator", "delivery manager"), ("OPT", "H-1B")),
        Role("Program Manager", ("program manager", "technical program manager", "tpm"), ("OPT", "H-1B")),
        Role("Scrum Master", ("scrum master", "agile coach", "release train engineer"), ("OPT", "H-1B")),
        Role("Product Owner", ("product owner", "associate product owner"), ("OPT", "H-1B")),
    )),
    Category("Sales & Business Development", "TrendingUp", (
        Role("Account Executive", ("account executive", "enterprise account executive", "sales executive"), ("OPT", "H-1B")),
        Role("Account Manager", ("account manager", "key account manager", "client account manager"), ("OPT", "H-1B")),
        Role("Sales Representative", ("sales representative", "inside sales representative", "field sales representative", "sales associate"), ()),
        Role("Business Development Rep", ("business development representative", "bdr", "sales development representative", "sdr"), ("OPT",)),
        Role("Sales / Solutions Engineer", ("sales engineer", "solutions engineer", "pre-sales engineer", "presales engineer"), ("OPT", "STEM", "H-1B")),
        Role("Customer Success Manager", ("customer success manager", "csm", "client success manager"), ("OPT", "H-1B")),
        Role("Sales Manager", ("sales manager", "regional sales manager", "territory manager", "sales director"), ("H-1B",)),
    )),
    Category("Human Resources & Recruiting", "Users", (
        Role("Recruiter", ("recruiter", "talent acquisition specialist", "technical recruiter", "talent acquisition partner", "sourcer"), ("OPT", "H-1B")),
        Role("HR Generalist", ("hr generalist", "human resources generalist", "hr coordinator", "people operations", "hr business partner", "hrbp"), ("OPT", "H-1B")),
        Role("HR Manager", ("hr manager", "human resources manager", "people operations manager", "hr director", "talent acquisition manager"), ("H-1B",)),
        Role("Compensation & Benefits Analyst", ("compensation analyst", "benefits analyst", "compensation and benefits", "total rewards analyst"), ("OPT", "H-1B")),
        Role("L&D Specialist", ("learning and development specialist", "l&d specialist", "training specialist", "instructional designer"), ("OPT", "H-1B")),
    )),
    Category("Operations & Supply Chain", "Package", (
        Role("Operations Manager", ("operations manager", "operations director", "business operations manager"), ("OPT", "H-1B")),
        Role("Operations Analyst", ("operations analyst", "business operations analyst", "process analyst"), ("OPT", "H-1B")),
        Role("Supply Chain Analyst", ("supply chain analyst", "supply chain manager", "demand planner", "supply planner"), ("OPT", "H-1B")),
        Role("Logistics Coordinator", ("logistics coordinator", "logistics manager", "transportation coordinator"), ()),
        Role("Procurement Specialist", ("procurement specialist", "buyer", "purchasing manager", "sourcing specialist", "category manager"), ("OPT",)),
        Role("Warehouse / Inventory Manager", ("warehouse manager", "inventory manager", "fulfillment manager", "production manager", "plant manager"), ()),
    )),
    Category("Customer Service & Support", "Headphones", (
        Role("Customer Service Representative", ("customer service representative", "customer support specialist", "call center agent", "customer care representative"), ()),
        Role("Technical Support Engineer", ("technical support engineer", "technical support specialist", "support engineer", "help desk technician", "it help desk"), ("OPT", "H-1B")),
        Role("Customer Experience Manager", ("customer experience manager", "client services manager", "support team lead", "customer support manager"), ("H-1B",)),
    )),
    Category("Skilled Trades & Construction", "HardHat", (
        Role("Electrician", ("electrician", "journeyman electrician", "industrial electrician"), ()),
        Role("Plumber", ("plumber", "pipefitter", "journeyman plumber"), ()),
        Role("HVAC Technician", ("hvac technician", "hvac installer", "refrigeration technician"), ()),
        Role("Welder", ("welder", "fabricator", "mig welder", "tig welder"), ()),
        Role("Carpenter", ("carpenter", "framer", "finish carpenter"), ()),
        Role("Maintenance Technician", ("maintenance technician", "facilities technician", "building maintenance", "maintenance mechanic"), ()),
        Role("Construction Project Manager", ("construction project manager", "site supervisor", "construction superintendent", "foreman"), ()),
        Role("CNC Machinist", ("cnc machinist", "machinist", "cnc operator"), ()),
        Role("Automotive Technician", ("automotive technician", "auto mechanic", "diesel mechanic", "service technician"), ()),
        Role("Heavy Equipment Operator", ("heavy equipment operator", "crane operator", "equipment operator"), ()),
    )),
    Category("Administrative & Office", "Inbox", (
        Role("Administrative Assistant", ("administrative assistant", "admin assistant", "office administrator", "administrative coordinator"), ()),
        Role("Executive Assistant", ("executive assistant", "ea", "personal assistant"), ("H-1B",)),
        Role("Office Manager", ("office manager", "office coordinator", "facilities coordinator"), ()),
        Role("Data Entry Clerk", ("data entry clerk", "data entry specialist", "records clerk"), ()),
    )),
    Category("Healthcare & Clinical", "Stethoscope", (
        Role("Registered Nurse", ("registered nurse", "rn", "staff nurse", "charge nurse"), ("H-1B",)),
        Role("Nurse Practitioner", ("nurse practitioner", "np", "advanced practice nurse"), ("H-1B",)),
        Role("Licensed Practical Nurse", ("licensed practical nurse", "lpn", "lvn"), ()),
        Role("Medical Assistant", ("medical assistant", "clinical assistant", "patient care technician"), ()),
        Role("Pharmacist", ("pharmacist", "clinical pharmacist", "staff pharmacist"), ("H-1B",)),
        Role("Physical Therapist", ("physical therapist", "pt", "occupational therapist"), ("H-1B",)),
        Role("Medical Billing & Coding", ("medical billing", "medical coder", "medical billing and coding specialist"), ()),
        Role("Healthcare Administrator", ("healthcare administrator", "health services manager", "practice manager", "clinical research coordinator"), ("OPT", "H-1B")),
        Role("Radiologic Technologist", ("radiologic technologist", "rad tech", "medical laboratory technician", "lab technician"), ()),
    )),
    Category("Engineering (Non-Software)", "Cog", (
        Role("Mechanical Engineer", ("mechanical engineer", "mechanical design engineer"), ("OPT", "STEM", "H-1B")),
        Role("Electrical Engineer", ("electrical engineer", "electronics engineer", "power systems engineer"), ("OPT", "STEM", "H-1B")),
        Role("Civil Engineer", ("civil engineer", "structural engineer", "geotechnical engineer"), ("OPT", "STEM", "H-1B")),
        Role("Industrial Engineer", ("industrial engineer", "process engineer", "manufacturing engineer"), ("OPT", "STEM", "H-1B")),
        Role("Chemical Engineer", ("chemical engineer", "process chemical engineer"), ("OPT", "STEM", "H-1B")),
        Role("Aerospace Engineer", ("aerospace engineer", "avionics engineer"), ("OPT", "STEM", "H-1B")),
        Role("Quality Engineer", ("quality engineer", "quality assurance engineer", "qa engineer manufacturing", "quality control engineer"), ("OPT", "STEM", "H-1B")),
        Role("Project Engineer", ("project engineer", "field engineer"), ("OPT", "STEM", "H-1B")),
        Role("Biomedical Engineer", ("biomedical engineer", "biomedical", "bme"), ("OPT", "STEM", "H-1B")),
        Role("Environmental Engineer", ("environmental engineer", "environmental scientist"), ("OPT", "STEM", "H-1B")),
    )),
    Category("Finance Extra", "Calculator", (
        Role("Investment Banking Analyst", ("investment banking analyst", "ib analyst", "m&a analyst"), ("H-1B",)),
        Role("FP&A Analyst", ("fp&a analyst", "financial planning and analysis", "treasury analyst"), ("OPT", "H-1B")),
        Role("Auditor", ("auditor", "internal auditor", "external auditor", "audit associate"), ("OPT", "H-1B")),
        Role("Tax Accountant", ("tax accountant", "tax associate", "tax analyst"), ("OPT", "H-1B")),
        Role("Bookkeeper", ("bookkeeper", "accounts payable", "accounts receivable", "payroll specialist"), ()),
    )),
)
