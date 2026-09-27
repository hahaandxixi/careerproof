"""Create reusable synthetic demo accounts and a published job on the local API."""

import json
from pathlib import Path

import httpx

from evals.demo_credentials import get_demo_credentials_pair

BASE = "http://127.0.0.1:8000/api/v1"
TITLE = "Python 后端开发实习生（合成演示）"


def data(response):
    response.raise_for_status()
    return response.json()["data"]


def seed():
    accounts = get_demo_credentials_pair()
    for role, name in (("student", "演示学生"), ("enterprise", "演示企业")):
        with httpx.Client(base_url=BASE, timeout=30, trust_env=False) as client:
            credentials = accounts[role]
            registered = client.post(
                "/auth/register", json={**credentials, "displayName": name, "role": role}
            )
            if registered.status_code != 409:
                data(registered)
            login = client.post("/auth/login", json=credentials)
            if login.status_code == 401:
                raise RuntimeError(
                    "Demo login failed; changing local credentials does not reset an existing "
                    "account password. Restore the original local credentials, or explicitly "
                    "configure two new demo email addresses. Existing accounts are left unchanged."
                )
            user = data(login)["user"]
            if user["role"] != role:
                raise RuntimeError("Existing demo account has a different role; left unchanged")
            print(f"Verified login: {credentials['email']} ({role})")
            if role == "enterprise":
                organizations = data(client.get("/enterprises/me"))
                organization = next(
                    (item for item in organizations if item["name"] == "CareerProof 合成演示企业"),
                    None,
                )
                if organization is None:
                    organization = data(
                        client.post(
                            "/enterprises",
                            json={
                                "name": "CareerProof 合成演示企业",
                                "description": "仅用于本地合成材料测试",
                            },
                        )
                    )
                catalog = json.loads(
                    (Path(__file__).resolve().parents[2] / "demo/jobs.json").read_text(
                        encoding="utf-8"
                    )
                )
                jobs = data(client.get("/jobs/mine", params={"q": "合成演示", "pageSize": 100}))[
                    "items"
                ]
                for spec in catalog:
                    job = next((item for item in jobs if item["title"] == spec["title"]), None)
                    if job is None:
                        job = data(
                            client.post(
                                "/jobs",
                                json={
                                    **spec,
                                    "companyName": organization["name"],
                                    "enterpriseId": organization["id"],
                                    "status": "published",
                                    "city": "深圳",
                                    "employmentType": "internship",
                                    "description": (
                                        "合成测试岗位，不是实际招聘。"
                                        "请以材料证据核验要求；缺少材料不代表没有能力。"
                                    ),
                                },
                            )
                        )
                    elif job["status"] != "published":
                        job = data(client.patch(f"/jobs/{job['id']}", json={"status": "published"}))
                    public_job = data(httpx.get(f"{BASE}/jobs/{job['id']}", trust_env=False))
                    assert public_job["status"] == "published"
                    assert len(public_job["requirements"]) == 5
                    print(f"Verified demo job: {spec['title']} {job['id']}")
            data(client.post("/auth/logout"))


if __name__ == "__main__":
    seed()
