"""NFR 5 accessibility audit (WCAG 2.1 AA).

Every main page is rendered, including pages with form errors, and its HTML is checked.
The colour pairs in style.css are checked for contrast.
"""
import re
from html.parser import HTMLParser
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from directory.models import Clinic, LicenseVerification, Therapist
from learning.models import Learner, TeacherProfile
from learning.services import answer, next_card, start_session
from screening.models import Question, ScreeningSession

PW = "CorrectHorse-42!"
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
NO_LABEL_NEEDED = {"hidden", "submit", "button", "reset", "image"}


# ---------- a small HTML tree ----------
class Node:
    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.children = []

    def iter(self):
        yield self
        for c in self.children:
            if isinstance(c, Node):
                yield from c.iter()

    def text(self):
        """Visible text, as a screen reader would read it (skips aria-hidden parts, uses img alt)."""
        if self.attrs.get("aria-hidden") == "true":
            return ""
        if self.tag == "img":
            return self.attrs.get("alt") or ""
        return " ".join(c.text() if isinstance(c, Node) else c for c in self.children).strip()

    def inside(self, tag):
        p = self.parent
        while p is not None:
            if p.tag == tag:
                return True
            p = p.parent
        return False


class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {}, None)
        self.current = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in VOID:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.current.children.append(Node(tag, attrs, self.current))

    def handle_endtag(self, tag):
        p = self.current
        while p is not None and p.tag != tag:
            p = p.parent
        if p is not None and p.parent is not None:
            self.current = p.parent

    def handle_data(self, data):
        if data.strip():
            self.current.children.append(data.strip())


def audit(html):
    """Return a list of WCAG problems found in one page."""
    b = TreeBuilder()
    b.feed(html)
    nodes = list(b.root.iter())
    problems = []
    by_id = {}
    for n in nodes:
        if "id" in n.attrs:
            if n.attrs["id"] in by_id:
                problems.append(f"duplicate id '{n.attrs['id']}' (4.1.1)")
            by_id[n.attrs["id"]] = n
    label_for = {n.attrs.get("for") for n in nodes if n.tag == "label"}

    html_tag = next((n for n in nodes if n.tag == "html"), None)
    if html_tag is None or not html_tag.attrs.get("lang"):
        problems.append("page language not set (3.1.1)")
    title = next((n for n in nodes if n.tag == "title"), None)
    if title is None or not title.text():
        problems.append("page has no title (2.4.2)")
    for n in nodes:
        if n.tag == "meta" and n.attrs.get("name") == "viewport":
            content = n.attrs.get("content", "").replace(" ", "")
            if "user-scalable=no" in content or "maximum-scale=1" in content:
                problems.append("zoom is blocked (1.4.4)")

    headings = [int(n.tag[1]) for n in nodes if re.fullmatch(r"h[1-6]", n.tag)]
    if headings.count(1) != 1:
        problems.append(f"expected one h1, found {headings.count(1)} (1.3.1)")
    for before, after in zip(headings, headings[1:]):
        if after > before + 1:
            problems.append(f"heading level skips from h{before} to h{after} (1.3.1)")

    for n in nodes:
        a = n.attrs
        if n.tag == "img" and "alt" not in a:
            problems.append(f"image without alt: {a.get('src')} (1.1.1)")
        if n.tag in ("input", "select", "textarea") and a.get("type") not in NO_LABEL_NEEDED:
            labelled = (a.get("id") in label_for or n.inside("label")
                        or a.get("aria-label") or a.get("aria-labelledby"))
            if not labelled:
                problems.append(f"form field without a label: {a.get('name') or a.get('id')} (1.3.1, 4.1.2)")
        if n.tag == "label" and "for" in a and a["for"] not in by_id:
            problems.append(f"label points to a missing field '{a['for']}' (1.3.1)")
        if n.tag == "button" and not (n.text() or a.get("aria-label")):
            problems.append("button without a name (4.1.2)")
        if n.tag == "a" and "href" in a and not (n.text() or a.get("aria-label")):
            problems.append(f"link without a name: {a['href']} (2.4.4)")
        for ref_attr in ("aria-describedby", "aria-labelledby"):
            for ref in a.get(ref_attr, "").split():
                if ref not in by_id:
                    problems.append(f"{ref_attr} points to a missing id '{ref}' (1.3.1)")
        if a.get("tabindex", "0").lstrip("-").isdigit() and int(a.get("tabindex", "0")) > 0:
            problems.append("positive tabindex changes the focus order (2.4.3)")
        if n.tag == "input" and a.get("name") in ("email", "password", "password_confirm", "full_name", "phone"):
            if not a.get("autocomplete"):
                problems.append(f"personal field '{a['name']}' has no autocomplete (1.3.5)")
    return problems


# ---------- colour contrast ----------
def luminance(hex_colour):
    h = hex_colour.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    hi, lo = sorted([luminance(a), luminance(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def css_variables(css, selector):
    """The --name: #hex values set in one CSS rule, e.g. ':root' or '.play.mode-dim'."""
    rule = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", rule.group(1)))


class ContrastTests(TestCase):
    """WCAG 1.4.3 (text, 4.5:1) and 1.4.11 (control borders and focus outlines, 3:1)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = (Path(settings.BASE_DIR) / "static" / "css" / "style.css").read_text(encoding="utf-8")
        cls.root = css_variables(cls.css, ":root")

    def check(self, pairs, colours):
        for fg, bg, need in pairs:
            a, b = colours.get(fg, fg), colours.get(bg, bg)
            with self.subTest(fg=fg, bg=bg):
                self.assertGreaterEqual(round(contrast(a, b), 2), need, f"{fg} on {bg}: {contrast(a, b):.2f}")

    def test_site_colours(self):
        text = 4.5
        self.check([
            ("text", "bg", text), ("text", "surface", text), ("muted", "bg", text), ("muted", "surface", text),
            ("primary-dark", "surface", text), ("primary-dark", "bg", text),          # links
            ("#ffffff", "primary", text), ("#ffffff", "primary-dark", text),          # buttons
            ("primary-dark", "secondary-bg", text),                                   # secondary buttons, tags
            ("error", "error-bg", text), ("success", "success-bg", text),
            ("warning", "warning-bg", text), ("info", "info-bg", text),
            ("#ffffff", "text", text),                                                # header
            ("control-border", "surface", 3), ("control-border", "bg", 3),
            ("control-border", "secondary-bg", 3), ("control-border", "text", 3),
            ("focus", "bg", 3), ("focus", "surface", 3), ("#ffffff", "text", 3),      # focus outlines
        ], self.root)

    def test_play_modes(self):
        base = {**self.root, **css_variables(self.css, ".play")}
        for mode in ("soft", "contrast", "dim"):
            colours = {**base, **(css_variables(self.css, f".play.mode-{mode}") if mode != "soft" else {})}
            with self.subTest(mode=mode):
                self.check([
                    ("card-fg", "card-bg", 4.5), ("choice-fg", "choice-bg", 4.5), ("ok", "ok-bg", 4.5),
                    ("hint", "hint-bg", 4.5), ("muted", "bg", 4.5), ("text", "bg", 4.5),
                    ("choice-border", "bg", 3), ("focus", "bg", 3), ("focus", "choice-bg", 3),
                ], colours)


# ---------- every main page ----------
@override_settings(AI_FLASHCARDS_ENABLED=False)
class PageAuditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_questions", verbosity=0)
        User = get_user_model()
        cls.therapist_user = User.objects.create_user(email="t@x.com", password=PW)
        cls.therapist = Therapist.objects.create(user=cls.therapist_user, full_name="Dr Wanjiru", phone="0700")
        clinic = Clinic.objects.create(name="Hope Clinic", address="Nairobi", latitude=-1.28,
                                       longitude=36.82, operating_hours="Mon-Fri")
        cls.therapist.clinics.add(clinic)
        LicenseVerification.objects.create(therapist=cls.therapist, license_number="L1",
                                           document="licenses/x.pdf", status="APPROVED")
        cls.clinic = clinic

        teacher_user = User.objects.create_user(email="teacher@x.com", password=PW, role=User.Role.TEACHER)
        cls.teacher = TeacherProfile.objects.create(user=teacher_user, full_name="Ms A", school_name="Hope")
        cls.learner = Learner.objects.create(teacher=cls.teacher, nickname="Amani")
        cls.admin = User.objects.create_superuser(email="admin@x.com", password=PW)

    def screen(self, risks):
        data = {"child_age_months": "20"}
        for i, q in enumerate(Question.objects.order_by("number")):
            risky_answer = "no" if q.is_reverse_scored else "yes"
            safe_answer = "yes" if q.is_reverse_scored else "no"
            data[f"q{q.id}"] = risky_answer if i < risks else safe_answer
        self.client.post(reverse("screening-questions"), data)
        return ScreeningSession.objects.latest("created_at")

    def assert_accessible(self, name, response):
        self.assertEqual(response.status_code, 200, name)
        problems = audit(response.content.decode())
        self.assertEqual(problems, [], f"{name}: {problems}")

    def test_public_pages(self):
        for name in ("home", "find", "login", "register", "teacher-register", "screening", "screening-questions"):
            with self.subTest(page=name):
                self.assert_accessible(name, self.client.get(reverse(name)))
        with self.subTest(page="therapist-detail"):
            self.assert_accessible("therapist-detail",
                                   self.client.get(reverse("therapist-detail", args=[self.therapist.pk])))
        for risks in (0, 4, 12):  # low, medium, high (high includes the referral search panel)
            session = self.screen(risks)
            with self.subTest(page=f"screening-result ({risks} risks)"):
                self.assert_accessible("screening-result",
                                       self.client.get(reverse("screening-result", args=[session.pk])))

    def test_pages_with_form_errors(self):
        cases = [
            ("login", {"email": "nobody@x.com", "password": "wrong"}),
            ("register", {"email": "not-an-email"}),
            ("teacher-register", {"full_name": ""}),
            ("screening-questions", {"child_age_months": "abc"}),
        ]
        for name, data in cases:
            with self.subTest(page=name):
                self.assert_accessible(name, self.client.post(reverse(name), data))

    def test_therapist_pages(self):
        self.client.force_login(self.therapist_user)
        for name, args in (("dashboard", []), ("clinic-add", []), ("clinic-edit", [self.clinic.pk]),
                           ("license-upload", [])):
            with self.subTest(page=name):
                self.assert_accessible(name, self.client.get(reverse(name, args=args)))
        with self.subTest(page="clinic-add with errors"):
            self.assert_accessible("clinic-add", self.client.post(reverse("clinic-add"), {"name": ""}))

    def test_teacher_pages(self):
        self.client.force_login(self.teacher.user)
        self.assert_accessible("teach", self.client.get(reverse("teach")))
        self.assert_accessible("teach with errors", self.client.post(reverse("teach"), {"nickname": ""}))
        self.assert_accessible("teach-start", self.client.get(reverse("teach-start", args=[self.learner.pk])))
        for mode in ("soft", "contrast", "dim"):
            session = start_session(self.teacher, self.learner, audio_enabled=True, sensory_mode=mode,
                                    planned_cards=6)
            with self.subTest(page=f"teach-play ({mode})"):
                self.assert_accessible("teach-play", self.client.get(reverse("teach-play", args=[session.pk])))
        card = next_card(session)
        answer(session, card["choices"][0])
        self.assert_accessible("teach-summary", self.client.get(reverse("teach-summary", args=[session.pk])))

    def test_audit_finds_problems(self):
        """The checker itself: a page with known problems must fail."""
        bad = ('<html><head><title></title></head><body><h1>A</h1><h3>B</h3><img src="x.png">'
               '<input name="email" id="e"><button></button><a href="/x"></a><p id="d"></p><p id="d"></p>'
               '<input id="q" aria-describedby="missing"></body></html>')
        problems = " | ".join(audit(bad))
        for expected in ("language", "title", "skips", "alt", "without a label", "button without",
                         "link without", "duplicate id", "missing id", "autocomplete"):
            self.assertIn(expected, problems)
