from uuid import uuid4

from app.agents.evidence_workflow import build_evidence_contexts
from app.tools.code_analyzer import ProjectFileSnapshot, find_evidence
from app.tools.matcher import RequirementInput, match_candidate


def test_python_business_methods_survive_candidate_selection():
    """A helper/exception class must not consume the file's only Python candidate.

    The frozen source has RegistrationService.register/cancel after a small
    exception class. A rule candidate that keeps only the first implemented
    function cannot support a requirement about registration and cancellation.
    """
    source = '''\
class DomainError(Exception):
    def __init__(self, message: str):
        self.message = message


class RegistrationService:
    def register(self, event_id: int, student_code: str):
        if not student_code:
            raise DomainError("missing student")
        return {"status": "active"}

    def cancel(self, registration_id: int):
        if registration_id < 1:
            raise DomainError("missing registration")
        return {"status": "cancelled"}
'''

    evidence = find_evidence(
        [ProjectFileSnapshot("service.py", source)],
        "Python",
    )
    snippets = "\n".join(item.snippet for item in evidence)

    assert "def register" in snippets
    assert "def cancel" in snippets


def test_unrelated_methods_do_not_crowd_out_business_evidence():
    source = '''\
class Helper:
    def __init__(self, value):
        self.value = value

    def format_label(self):
        return str(self.value)

    def unused_helper(self):
        return "unrelated"


class Service:
    def register(self, event_id, student_code):
        if not student_code:
            raise ValueError("missing student")
        connection.execute("UPDATE events SET remaining = remaining - 1")
        return {"status": "active"}

    def cancel(self, registration_id):
        if registration_id < 1:
            raise ValueError("missing registration")
        connection.execute("UPDATE events SET remaining = remaining + 1")
        return {"status": "cancelled"}
'''
    evidence = find_evidence(
        [ProjectFileSnapshot("service.py", source)],
        "Python",
        "实现报名、取消和名额恢复业务",
    )
    snippets = "\n".join(item.snippet for item in evidence)

    assert "def register" in snippets
    assert "def cancel" in snippets
    assert len(evidence) <= 4


def test_bounded_context_keeps_business_methods_within_citation_cap():
    service = '''\
class Service:
    def register(self, event_id, student_code):
        if not student_code:
            raise ValueError("missing student")
        connection.execute("UPDATE events SET remaining = remaining - 1")
        return {"status": "active"}

    def cancel(self, registration_id):
        if registration_id < 1:
            raise ValueError("missing registration")
        connection.execute("UPDATE events SET remaining = remaining + 1")
        return {"status": "cancelled"}
'''
    api = '''\
def create_app():
    return {"app": True}
'''
    result = match_candidate(
        [RequirementInput(uuid4(), "实现报名、取消和名额恢复业务", "Python", 5)],
        [],
        [
            ProjectFileSnapshot("api.py", api),
            ProjectFileSnapshot("service.py", service),
        ],
    )
    contexts = build_evidence_contexts(result, max_evidence=2)
    snippets = "\n".join(item.snippet for item in contexts[0].evidence)

    assert "def register" in snippets
    assert "def cancel" in snippets
    assert len(contexts[0].evidence) <= 2
