#!/usr/bin/env python3
"""
Generate fixture files representing what the LLM extraction layer returns.

These let the whole pipeline (matching, scoring, ranking, blocking rules) be
tested and regression-checked without an API key or network access. They are
hand-authored to match the sample CVs in data/sample_cvs/.

When you have a real LLM configured, regenerate these from actual model output
so your regression tests track the model you're really running:

    LLM_PROVIDER=anthropic python make_fixtures.py --from-model
"""

import json
from pathlib import Path

FIX = Path("data/fixtures")
FIX.mkdir(parents=True, exist_ok=True)


def cv(match, name, email, age, quals, exp, skills, notes=None):
    return {
        "match": match,
        "output": {
            "candidate": {"name": name, "email": email, "phone": None,
                          "location": None, "age": age, "date_of_birth": None},
            "qualifications": quals,
            "experience": exp,
            "skills": skills,
            "certifications": [],
            "languages": [],
            "extraction_notes": notes,
        },
    }


def q(title, level, field, inst=None, year=None, done=True):
    return {"degree_title": title, "level": level, "field_of_study": field,
            "institution": inst, "completion_year": year, "is_completed": done}


def e(title, employer, etype, years, desc, tech, current=False):
    return {"job_title": title, "employer": employer, "employment_type": etype,
            "start_date": None, "end_date": None, "is_current": current,
            "duration_years": years, "description": desc, "technologies": tech}


FIXTURES = [
    cv("AYESHA KHAN", "Ayesha Khan", "ayesha.khan@example.com", None,
       [q("BSc Mechanical Engineering", "bachelors", "Mechanical Engineering",
          "University of Engineering & Technology, Lahore", 2020)],
       [e("Design Engineer", "Indus Motor Company", "full_time", 3.4,
          "Produced 3D models and detailed manufacturing drawings for interior trim and "
          "bracket assemblies. Applied GD&T to all released drawings and reviewed supplier "
          "drawing submissions. Ran tolerance stack-up analysis on door hardware assemblies "
          "and supported DFM reviews with the tooling team. Reduced part cost 14% on a "
          "localisation project for seat brackets.",
          ["SolidWorks", "Auto CAD", "GD&T"], current=True),
        e("Design Intern", "Millat Tractors Ltd.", "internship", 0.6,
          "Assisted senior engineers with 2D drafting and bill-of-material preparation for "
          "transmission housing components.", [])],
       ["Solid Works", "Auto CAD", "GD&T", "Design for Manufacturing",
        "Tolerance Analysis", "Technical Documentation", "MS Excel"]),

    cv("BILAL AHMED", "Bilal Ahmed", "bilal.ahmed@example.com", None,
       [q("BS Mechatronics Engineering", "bachelors", "Mechatronics Engineering",
          "Air University Islamabad", 2019)],
       [e("CAD Engineer", "Ghandhara Industries", "full_time", 5.0,
          "Created detailed part and assembly models for commercial vehicle chassis "
          "components using Autodesk Inventor. Prepared production drawings to ISO standards "
          "and worked with the machine shop on manufacturability feedback. Led the migration "
          "of the legacy drawing archive to a managed PDM system.",
          ["Autodesk Inventor", "CATIA V5", "PDM"])],
       ["Autodesk Inventor", "CATIA V5", "geometric dimensioning and tolerancing",
        "manufacturing drawings", "PDM systems", "MATLAB"]),

    cv("FATIMA RAZA", "Fatima Raza", "fatima.raza@example.com", None,
       [q("Master of Science in Mechanical Engg", "masters", "Mechanical Engineering",
          "NUST Islamabad", 2023),
        q("Bachelor of Science in Mechanical Engineering", "bachelors",
          "Mechanical Engineering", "NUST Islamabad", 2021)],
       [e("Graduate Trainee Engineer", "Pak Suzuki Motor Co.", "full_time", 1.0,
          "Rotational programme across press shop, weld shop and quality. Currently "
          "supporting the body engineering team with 3D modelling of reinforcement panels "
          "and checking supplier drawings for GD&T compliance.",
          ["CATIA", "GD&T"], current=True),
        e("Research Assistant", "NUST Advanced Manufacturing Lab", "part_time", 2.0,
          "Finite element analysis of lightweight automotive structures. Published two "
          "conference papers on crash energy absorption in extruded aluminium members.",
          ["ANSYS", "MATLAB"])],
       ["CATIA", "ANSYS", "SolidWorks", "GD&T", "Finite Element Analysis",
        "MATLAB", "technical report writing"]),

    cv("HAMZA YOUSUF", "Hamza Yousuf", "hamza.yousuf@example.com", None,
       [q("BBA (Hons) Finance", "bachelors", "Finance",
          "Institute of Business Administration, Karachi", 2018)],
       [e("Senior Accountant", "Nishat Chunian Group", "full_time", 7.0,
          "Managed accounts payable and receivable for the textile division. Prepared "
          "monthly management accounts and supported the annual audit. Implemented a "
          "revised expense approval workflow in SAP.",
          ["SAP FICO"], current=True)],
       ["SAP FICO", "financial reporting", "accounts payable", "MS Excel",
        "taxation", "internal controls"]),

    cv("SANA MALIK", "Sana Malik", "sana.malik@example.com", 24,
       [q("B.E. Mechanical Engineering", "bachelors", "Mechanical Engineering",
          "Mehran University of Engineering & Technology", 2023)],
       [e("Junior Design Engineer", "Master Motor Corporation", "full_time", 2.0,
          "Support the design team on bracket and mounting component design for light "
          "commercial vehicles. Prepare 2D manufacturing drawings and maintain the part "
          "numbering database. Assisted on two localisation projects.",
          ["AutoCAD", "SolidWorks"], current=True),
        e("Internship", "Atlas Honda Ltd", "internship", 0.25,
          "Three month summer internship in the manufacturing engineering department. "
          "Documented assembly line standard operating procedures.", [])],
       ["AutoCAD", "SolidWorks", "technical drawing", "GD and T", "MS Office"]),
]


JD_FIXTURES = [
    {
        "match": "Mechanical Design Engineer\nHonda Atlas Cars",
        "output": {
            "job_title": "Mechanical Design Engineer",
            "summary": "Component design for passenger vehicle assemblies.",
            "responsibilities_text": (
                "Produce 3D models and 2D manufacturing drawings for vehicle components. "
                "Apply GD&T standards to drawings and review supplier submissions. Support "
                "design validation, tolerance stack-up analysis and DFM reviews. Work with "
                "the production and quality teams to resolve manufacturing issues. "
                "Contribute to cost reduction and part localisation projects."
            ),
            "required_skills": ["AutoCAD", "SolidWorks", "GD&T",
                                "Design for Manufacturing (DFM)", "Technical Documentation"],
            "preferred_skills": ["CATIA", "Six Sigma", "Tolerance stack-up analysis"],
            "requirements": {
                "qualification": {
                    "mentioned": True,
                    "quoted_text": "Bachelor's degree in Mechanical Engineering from an HEC-recognised university.",
                    "min_value": None, "max_value": None,
                    "level": "bachelors", "field_of_study": "Mechanical Engineering"},
                "experience": {
                    "mentioned": True,
                    "quoted_text": "2-4 years of relevant experience in automotive, manufacturing or product design.",
                    "min_value": 2, "max_value": 4, "level": None, "field_of_study": None},
                "age": {
                    "mentioned": True,
                    "quoted_text": "Applicants should be between 22 and 30 years of age.",
                    "min_value": 22, "max_value": 30, "level": None, "field_of_study": None},
            },
        },
    },
    {
        # Deliberately missing experience AND age — exercises the blocking rule.
        "match": "Production Engineer\nHonda Atlas Cars",
        "output": {
            "job_title": "Production Engineer",
            "summary": "Support assembly line operations and continuous improvement.",
            "responsibilities_text": (
                "Monitor line performance, cycle times and takt adherence. Lead Kaizen "
                "events and 5S implementation on assigned lines. Investigate line stoppages "
                "and implement countermeasures. Prepare production reports for management."
            ),
            "required_skills": ["Lean Manufacturing", "Production Planning",
                                "Root Cause Analysis", "MS Excel", "Kaizen"],
            "preferred_skills": [],
            "requirements": {
                "qualification": {
                    "mentioned": True,
                    "quoted_text": "Bachelor's degree in Industrial or Mechanical Engineering.",
                    "min_value": None, "max_value": None,
                    "level": "bachelors", "field_of_study": "Industrial or Mechanical Engineering"},
                "experience": {"mentioned": False, "quoted_text": None, "min_value": None,
                               "max_value": None, "level": None, "field_of_study": None},
                "age": {"mentioned": False, "quoted_text": None, "min_value": None,
                        "max_value": None, "level": None, "field_of_study": None},
            },
        },
    },
]


def main() -> None:
    for i, f in enumerate(FIXTURES + JD_FIXTURES):
        name = f["match"].split("\n")[0].lower().replace(" ", "_")
        (FIX / f"{i:02d}_{name}.json").write_text(
            json.dumps(f, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    print(f"Wrote {len(FIXTURES) + len(JD_FIXTURES)} fixtures to {FIX}/")


if __name__ == "__main__":
    main()
