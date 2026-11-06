"""Student reads the current report before explicitly consenting in API tests."""


async def application_payload(student, report_id, *, share_consent=True):
    response = await student.get(f"/api/v1/match-reports/{report_id}")
    assert response.status_code == 200, response.text
    report = response.json()["data"]
    return {
        "reportId": str(report_id),
        "shareConsent": share_consent,
        "expectedReviewRevision": report["reviewRevision"],
    }
