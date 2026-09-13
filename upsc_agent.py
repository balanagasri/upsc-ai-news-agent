import os
import json
import re
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
import smtplib
import html

from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


# ============================================================
# 1. FETCH NEWS
# ============================================================

queries = [
    "India government policy",
    "India economy RBI",
    "Supreme Court India",
    "India environment climate",
    "India science technology",
    "India international relations",
    "India government schemes"
]

articles = []


for query in queries:

    encoded_query = urllib.parse.quote(query)

    rss_url = (
        "https://news.google.com/rss/search?"
        f"q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
    )

    try:

        with urllib.request.urlopen(
            rss_url,
            timeout=20
        ) as response:

            xml_data = response.read()

        root = ET.fromstring(xml_data)

        for item in root.findall(".//item")[:5]:

            title = item.findtext(
                "title",
                ""
            )

            link = item.findtext(
                "link",
                ""
            )

            description = item.findtext(
                "description",
                ""
            )

            source_element = item.find("source")

            if source_element is not None:
                source_name = source_element.text or ""
            else:
                source_name = ""

            articles.append(
                {
                    "title": title,
                    "link": link,
                    "description": description,
                    "source": source_name
                }
            )

    except Exception as e:

        print(
            f"Could not fetch '{query}': {e}"
        )


# ============================================================
# 2. REMOVE DUPLICATES
# ============================================================

unique_articles = {}


for article in articles:

    title = article["title"].strip()

    if title:

        unique_articles[title] = article


articles = list(
    unique_articles.values()
)


print(
    f"Collected {len(articles)} unique articles."
)


if not articles:

    raise Exception(
        "No news articles were collected."
    )


# ============================================================
# 3. PREPARE NEWS FOR GEMINI
# ============================================================

news_text = ""


for i, article in enumerate(
    articles[:30],
    1
):

    news_text += (
        f"\nARTICLE {i}\n"
        f"TITLE: {article['title']}\n"
        f"SOURCE NAME: {article['source']}\n"
        f"DESCRIPTION: {article['description']}\n"
        f"SOURCE URL: {article['link']}\n"
        f"--------------------------------------------------\n"
    )


# ============================================================
# 4. GEMINI PROMPT
# ============================================================

prompt = f"""
You are an expert UPSC Civil Services Examination
current-affairs analyst.

Create a concise, accurate daily UPSC current-affairs
briefing from the supplied news articles.

============================================================
IMPORTANT ACCURACY RULES
============================================================

1. Do not invent facts.

2. Use ONLY facts that are explicitly supported by the supplied
news articles. Do not add facts from your general knowledge.

3. Do not claim that a government action, Supreme Court order,
RBI decision, policy, scheme, statistic or international event
happened unless the supplied article supports it.

4. Do not invent dates, numbers, statistics, names, locations,
government departments, court orders, laws, schemes, reports,
rankings, organizations or policy details.

5. If an important fact cannot be established from the supplied
material, write "Requires verification." Do not guess.

6. Clearly distinguish between:
   - what actually happened,
   - what a person or organization said,
   - what is proposed or expected,
   - and what is analysis or opinion.

7. Never convert a proposal, recommendation, discussion, criticism,
prediction or statement into a confirmed government decision or
implemented policy.

8. For Supreme Court or other court-related news, do not invent
case names, judgment details, constitutional provisions, legal
principles or court directions unless supported by the article.

9. For RBI, economy and government-policy news, do not invent
percentages, dates, monetary values, policy changes, decisions or
economic indicators.

10. For international relations, do not assume that a meeting,
agreement, treaty, conflict, visit or diplomatic decision occurred
unless supported by the supplied article.

11. For environment, climate, biodiversity and science topics, do not
invent species, locations, measurements, scientific findings,
project details, classifications or government actions.

12. For UPSC Prelims Facts, include only facts directly supported by
the supplied articles. If there are not enough verified facts,
prefer simpler supported facts rather than guessing.

13. For MCQs, every correct answer and explanation must be directly
supported by the supplied current-affairs material or by a clearly
stated concept contained in that material. Never create a question
whose answer depends on an unsupported factual claim.

14. For Quick Revision Points, include only information already
established in the selected topics. Do not introduce new facts.

15. For the Mains Angle and Mains Practice Question, base the issue
on the supplied article. Do not introduce an unrelated factual claim.

16. Do not confuse a news organization's reporting or opinion with
an official government source. If an article reports what someone
said, attribute it clearly.

17. Use the supplied source URL exactly. Do not change, shorten,
invent or replace the URL.

18. If the supplied article is insufficient to establish a claim,
say "Requires verification." rather than completing the claim from
memory.

19. Accuracy is more important than completeness. It is better to
omit a detail than provide an uncertain or fabricated detail.

20. Do not manufacture information merely to fill a required section.
If a section cannot be supported, keep it concise and state
"Requires verification." where appropriate.

21. Select topics based on UPSC importance, not simply because an
article is available.

22. Before finalizing each topic, internally check every factual
claim against the supplied article(s). Remove unsupported claims.

============================================================
============================================================
PRIORITIZE
============================================================

- Indian Polity
- Constitution
- Governance
- Judiciary
- Government schemes
- Economy
- Banking and RBI
- Environment
- Climate change
- Biodiversity
- Agriculture
- Science and Technology
- International Relations
- Internal Security
- Social Issues
- Important reports and indices

============================================================
IGNORE
============================================================

- Sports
- Entertainment
- Celebrity news
- Gossip
- Advertisements
- Trivial local news
- Sensational stories with little UPSC relevance

============================================================
NUMBER OF TOPICS
============================================================

Select approximately 5-8 genuinely important UPSC topics.

Do not select a topic merely because it is available.

Prioritize quality and UPSC relevance.

============================================================
EXACT OUTPUT FORMAT
============================================================

For every selected topic use EXACTLY this structure:

### TOPIC: <clear topic title>

**Category:** <category>

**UPSC Relevance Score:** <score>/100

**What Happened:**
Explain in 2-4 concise sentences.

**Quick Summary:**
- <short key takeaway>
- <short key takeaway>
- <short key takeaway>

Each Quick Summary bullet must be approximately
8-18 words.

Do not make the three bullets repetitive.

**Why It Matters for UPSC:**
Explain in 2-4 concise sentences.

**GS Paper:**
GS-1, GS-2, GS-3, GS-4 or Essay.

**Prelims Facts:**
1. Useful fact.
2. Useful fact.
3. Useful fact.

Exactly 3 facts.

Do NOT add a fourth numbered item.

**Mains Angle:**
Write one analytical UPSC-style Mains question.

**Source:**
Article title - source name.

**Source URL:**
EXACT SOURCE URL copied from the supplied article data.

IMPORTANT:
Keep Source and Source URL as separate labelled lines.

Do not write the article title again on a separate line.

============================================================
TOP 5 QUICK REVISION
============================================================

At the end provide:

### TOP 5 QUICK REVISION POINTS

1. ...
2. ...
3. ...
4. ...
5. ...

Exactly 5 points.

============================================================
PRELIMS MCQs
============================================================

Then provide:

### PRELIMS MCQS

Create exactly 3 MCQs.

Each MCQ must contain:

#### MCQ 1

**Question:** <question>

A) ...
B) ...
C) ...
D) ...

**Correct Answer:** X

**Explanation:** One concise explanation.

Then MCQ 2 and MCQ 3.

Make the MCQs based primarily on the supplied current-affairs
material and UPSC-relevant concepts.

============================================================
MAINS PRACTICE QUESTION
============================================================

Finally provide:

### MAINS PRACTICE QUESTION

One UPSC-style analytical question suitable for Mains.

Do NOT write a 150-250 word answer.

Write only the question.

============================================================
NEWS ARTICLES
============================================================

{news_text}
"""


# ============================================================
# 5. CALL GEMINI
# ============================================================

api_key = os.environ["GEMINI_API_KEY"]


gemini_url = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-3.5-flash:generateContent"
)


request_body = {

    "contents": [

        {
            "parts": [

                {
                    "text": prompt
                }

            ]
        }

    ]

}


request = urllib.request.Request(

    gemini_url,

    data=json.dumps(
        request_body
    ).encode("utf-8"),

    headers={
        "Content-Type": "application/json",
        "x-goog-api-key": api_key
    },

    method="POST"
)


try:

    with urllib.request.urlopen(
        request,
        timeout=120
    ) as response:

        result = json.loads(
            response.read().decode(
                "utf-8"
            )
        )


except urllib.error.HTTPError as e:

    print(
        f"Gemini API returned HTTP {e.code}"
    )

    print(
        e.read().decode(
            "utf-8"
        )
    )

    raise


# ============================================================
# 6. EXTRACT GEMINI RESPONSE
# ============================================================

try:

    briefing = (
        result["candidates"][0]
        ["content"]["parts"][0]["text"]
    )

except Exception:

    print(
        "Unexpected Gemini response:"
    )

    print(
        json.dumps(
            result,
            indent=2
        )
    )

    raise


print(
    "\n===================================="
)

print(
    "UPSC DAILY CURRENT AFFAIRS"
)

print(
    "====================================\n"
)

print(
    briefing
)


# ============================================================
# 7. DATE — INDIA TIME
# ============================================================

IST = timezone(
    timedelta(
        hours=5,
        minutes=30
    )
)


today = datetime.now(
    IST
).strftime(
    "%d %B %Y"
)


# ============================================================
# 8. HTML FORMATTING HELPERS
# ============================================================

def clean_text(text):

    text = text.strip()

    text = re.sub(
        r"^\s*[-*]\s+",
        "",
        text
    )

    text = html.escape(
        text
    )

    text = re.sub(
        r"\*\*(.*?)\*\*",
        r"<strong>\1</strong>",
        text
    )

    text = re.sub(
        r"(?<!\*)\*(?!\s)(.*?)(?<!\s)\*",
        r"<em>\1</em>",
        text
    )

    text = text.replace(
        "*",
        ""
    )

    return text


def extract_link(text):

    match = re.search(
        r"https?://[^\s)\]>]+",
        text
    )

    if match:

        return match.group(
            0
        ).rstrip(
            ".,;:!?\"'"
        )

    return ""


def remove_markdown_link(text):

    text = re.sub(
        r"\[([^\]]+)\]\([^)]+\)",
        r"\1",
        text
    )

    return text


def normalize_source_text(text):

    text = remove_markdown_link(
        text
    )

    text = re.sub(
        r"https?://[^\s]+",
        "",
        text
    )

    text = text.strip()

    return text


# ============================================================
# 9. BUILD BEAUTIFUL HTML
# ============================================================

def build_html(briefing):

    lines = (
        briefing
        .replace("\r", "")
        .split("\n")
    )

    output = []

    current_topic_open = False
    current_special_open = False

    list_type = None

    current_source_name = ""
    current_source_url = ""

    pending_source_name = False
    pending_source_url = False


    # --------------------------------------------------------
    # CLOSE NUMBERED LIST
    # --------------------------------------------------------

    def close_list():

        nonlocal list_type

        if list_type == "facts":

            output.append(
                "</ol>"
            )

        elif list_type == "summary":

            output.append(
                "</ul>"
            )

        elif list_type == "revision":

            output.append(
                "</ol>"
            )

        list_type = None


    # --------------------------------------------------------
    # CLOSE SOURCE BOX
    # --------------------------------------------------------

    def close_source_box():

        nonlocal current_source_name
        nonlocal current_source_url
        nonlocal pending_source_name
        nonlocal pending_source_url

        if (
            current_source_name
            or current_source_url
        ):

            source_name = (
                current_source_name
                or "Source article"
            )

            if current_source_url:

                output.append(
                    f"""
                    <div class="source-box">

                        <div class="source-label">
                            🔗 Source
                        </div>

                        <div class="source-name">
                            {clean_text(source_name)}
                        </div>

                        <a
                            class="source-button"
                            href="{html.escape(current_source_url, quote=True)}"
                            target="_blank"
                            rel="noopener noreferrer"
                        >
                            Read Source →
                        </a>

                    </div>
                    """
                )

            else:

                output.append(
                    f"""
                    <div class="source-box">

                        <div class="source-label">
                            🔗 Source
                        </div>

                        <div class="source-name">
                            {clean_text(source_name)}
                        </div>

                    </div>
                    """
                )

        current_source_name = ""
        current_source_url = ""

        pending_source_name = False
        pending_source_url = False


    # --------------------------------------------------------
    # CLOSE TOPIC
    # --------------------------------------------------------

    def close_topic():

        nonlocal current_topic_open

        close_list()
        close_source_box()

        if current_topic_open:

            output.append(
                "</div>"
            )

            output.append(
                "</div>"
            )

            current_topic_open = False


    # --------------------------------------------------------
    # CLOSE SPECIAL
    # --------------------------------------------------------

    def close_special():

        nonlocal current_special_open

        close_list()

        if current_special_open:

            output.append(
                "</div>"
            )

            output.append(
                "</div>"
            )

            current_special_open = False


    # ========================================================
    # PROCESS LINES
    # ========================================================

    for raw_line in lines:

        line = raw_line.strip()


        # ----------------------------------------------------
        # EMPTY LINE
        # ----------------------------------------------------

        if not line:

            close_list()

            continue


        # ----------------------------------------------------
        # PENDING SOURCE NAME
        # ----------------------------------------------------

        if pending_source_name:

            if re.search(
                r"\*\*Source URL:\*\*",
                line,
                re.IGNORECASE
            ):

                pending_source_name = False
                pending_source_url = True

                url_match = re.search(
                    r"\*\*Source URL:\*\*\s*(.*)",
                    line,
                    re.IGNORECASE
                )

                if url_match:

                    value = url_match.group(
                        1
                    ).strip()

                    url = extract_link(
                        value
                    )

                    if url:

                        current_source_url = url

                        close_source_box()

                continue


            if extract_link(line):

                current_source_url = (
                    extract_link(line)
                )

                pending_source_name = False

                close_source_box()

                continue


            current_source_name = (
                normalize_source_text(line)
            )

            pending_source_name = False

            continue


        # ----------------------------------------------------
        # PENDING SOURCE URL
        # ----------------------------------------------------

        if pending_source_url:

            url = extract_link(
                line
            )

            if url:

                current_source_url = url

                pending_source_url = False

                close_source_box()

                continue


        # ----------------------------------------------------
        # TOPIC
        # ----------------------------------------------------

        topic_match = re.match(
            r"^###\s*TOPIC\s*:?\s*(.*)$",
            line,
            re.IGNORECASE
        )

        if topic_match:

            close_special()
            close_topic()

            title = topic_match.group(
                1
            ).strip()

            output.append(
                f"""
                <div class="topic-card">

                    <div class="topic-title">
                        {clean_text(title)}
                    </div>

                    <div class="topic-body">
                """
            )

            current_topic_open = True

            continue


        # ----------------------------------------------------
        # QUICK REVISION
        # ----------------------------------------------------

        if re.match(
            r"^###\s*TOP 5 QUICK REVISION POINTS",
            line,
            re.IGNORECASE
        ):

            close_topic()
            close_special()

            output.append(
                """
                <div class="special-card revision-card">

                    <div class="special-title">
                        ⚡ Top 5 Quick Revision Points
                    </div>

                    <div class="special-body">
                """
            )

            current_special_open = True

            continue


        # ----------------------------------------------------
        # MCQS
        # ----------------------------------------------------

        if re.match(
            r"^###\s*PRELIMS MCQS",
            line,
            re.IGNORECASE
        ):

            close_topic()
            close_special()

            output.append(
                """
                <div class="special-card mcq-card">

                    <div class="special-title">
                        ❓ Prelims MCQs
                    </div>

                    <div class="special-body">
                """
            )

            current_special_open = True

            continue


        # ----------------------------------------------------
        # MAINS
        # ----------------------------------------------------

        if re.match(
            r"^###\s*MAINS PRACTICE QUESTION",
            line,
            re.IGNORECASE
        ):

            close_topic()
            close_special()

            output.append(
                """
                <div class="special-card mains-card">

                    <div class="special-title">
                        ✍️ Mains Practice Question
                    </div>

                    <div class="special-body">
                """
            )

            current_special_open = True

            continue


        # ----------------------------------------------------
        # MCQ NUMBER
        # ----------------------------------------------------

        mcq_match = re.match(
            r"^####\s*(MCQ\s*\d+)",
            line,
            re.IGNORECASE
        )

        if mcq_match:

            close_list()

            title = mcq_match.group(
                1
            )

            output.append(
                f"""
                <div class="mcq-title">
                    {clean_text(title)}
                </div>
                """
            )

            continue


        # ----------------------------------------------------
        # QUICK SUMMARY HEADING
        # ----------------------------------------------------

        summary_match = re.search(
            r"\*\*Quick Summary:\*\*",
            line,
            re.IGNORECASE
        )

        if summary_match:

            close_list()

            output.append(
                """
                <div class="section-heading">
                    💡 Quick Summary
                </div>

                <ul class="summary-list">
                """
            )

            list_type = "summary"

            continue


        # ----------------------------------------------------
        # SECTION HEADINGS
        # ----------------------------------------------------

        heading_match = re.match(
            r"^####\s+(.+)$",
            line
        )

        if heading_match:

            close_list()

            heading = heading_match.group(
                1
            ).strip()

            heading = re.sub(
                r"^\d+\.\s*",
                "",
                heading
            )

            heading_lower = heading.lower()

            if "what happened" in heading_lower:

                icon = "📰"

            elif "why it matters" in heading_lower:

                icon = "🎯"

            elif "prelims facts" in heading_lower:

                icon = "📌"

            elif "mains angle" in heading_lower:

                icon = "✍️"

            elif "source" in heading_lower:

                icon = "🔗"

            else:

                icon = "▸"

            output.append(
                f"""
                <div class="section-heading">
                    {icon} {clean_text(heading)}
                </div>
                """
            )

            continue


        # ----------------------------------------------------
        # CATEGORY
        # ----------------------------------------------------

        category_match = re.search(
            r"\*\*Category:\*\*\s*(.*)",
            line,
            re.IGNORECASE
        )

        if category_match:

            close_list()

            value = category_match.group(
                1
            ).strip()

            output.append(
                f"""
                <span class="badge category">
                    🏷️ {clean_text(value)}
                </span>
                """
            )

            continue


        # ----------------------------------------------------
        # RELEVANCE SCORE
        # ----------------------------------------------------

        relevance_match = re.search(
            r"\*\*UPSC Relevance Score:\*\*\s*(.*)",
            line,
            re.IGNORECASE
        )

        if relevance_match:

            close_list()

            value = relevance_match.group(
                1
            ).strip()

            output.append(
                f"""
                <span class="badge relevance">
                    🎯 UPSC Relevance: {clean_text(value)}
                </span>
                """
            )

            continue


        # ----------------------------------------------------
        # GS PAPER
        # ----------------------------------------------------

        gs_match = re.search(
            r"\*\*GS Paper:\*\*\s*(.*)",
            line,
            re.IGNORECASE
        )

        if gs_match:

            close_list()

            value = gs_match.group(
                1
            ).strip()

            output.append(
                f"""
                <span class="badge gs">
                    📚 {clean_text(value)}
                </span>
                """
            )

            continue


        # ----------------------------------------------------
        # SOURCE
        # ----------------------------------------------------

        source_match = re.search(
            r"\*\*Source:\*\*\s*(.*)",
            line,
            re.IGNORECASE
        )

        if source_match:

            close_list()

            value = source_match.group(
                1
            ).strip()

            if value:

                url = extract_link(
                    value
                )

                clean_source = normalize_source_text(
                    value
                )

                current_source_name = (
                    clean_source
                )

                if url:

                    current_source_url = url

                    close_source_box()

                else:

                    pending_source_name = False

            else:

                pending_source_name = True

            continue


        # ----------------------------------------------------
        # SOURCE URL
        # ----------------------------------------------------

        source_url_match = re.search(
            r"\*\*Source URL:\*\*\s*(.*)",
            line,
            re.IGNORECASE
        )

        if source_url_match:

            close_list()

            value = source_url_match.group(
                1
            ).strip()

            if value:

                url = extract_link(
                    value
                )

                if url:

                    current_source_url = url

                    close_source_box()

            else:

                pending_source_url = True

            continue


        # ----------------------------------------------------
        # ARTICLE TITLE OLD FORMAT
        # ----------------------------------------------------

        article_match = re.search(
            r"\*\*Article Title:\*\*\s*(.*)",
            line,
            re.IGNORECASE
        )

        if article_match:

            close_list()

            value = article_match.group(
                1
            ).strip()

            output.append(
                f"""
                <div class="article-title">
                    📰 {clean_text(value)}
                </div>
                """
            )

            continue


        # ----------------------------------------------------
        # OLD SOURCE LINK FORMAT
        # ----------------------------------------------------

        if re.search(
            r"\*\*Source Link:\*\*",
            line,
            re.IGNORECASE
        ):

            close_list()

            continue


        # ----------------------------------------------------
        # CORRECT ANSWER
        # ----------------------------------------------------

        answer_match = re.search(
            r"\*\*Correct Answer:\*\*\s*(.*)",
            line,
            re.IGNORECASE
        )

        if answer_match:

            close_list()

            value = answer_match.group(
                1
            ).strip()

            output.append(
                f"""
                <div class="answer-box">

                    <strong>
                        ✅ Correct Answer:
                    </strong>

                    {clean_text(value)}

                </div>
                """
            )

            continue


        # ----------------------------------------------------
        # EXPLANATION
        # ----------------------------------------------------

        explanation_match = re.search(
            r"\*\*Explanation:\*\*\s*(.*)",
            line,
            re.IGNORECASE
        )

        if explanation_match:

            close_list()

            value = explanation_match.group(
                1
            ).strip()

            output.append(
                f"""
                <div class="explanation">

                    <strong>
                        Explanation:
                    </strong>

                    {clean_text(value)}

                </div>
                """
            )

            continue


        # ----------------------------------------------------
        # MCQ QUESTION
        # ----------------------------------------------------

        question_match = re.search(
            r"\*\*Question:\*\*\s*(.*)",
            line,
            re.IGNORECASE
        )

        if question_match:

            close_list()

            value = question_match.group(
                1
            ).strip()

            output.append(
                f"""
                <div class="mcq-question">
                    {clean_text(value)}
                </div>
                """
            )

            continue


        # ----------------------------------------------------
        # MCQ OPTIONS
        # ----------------------------------------------------

        option_match = re.match(
            r"^([A-D])\)\s*(.*)",
            line
        )

        if option_match:

            close_list()

            letter = option_match.group(
                1
            )

            value = option_match.group(
                2
            )

            output.append(
                f"""
                <div class="option">

                    <span class="option-letter">
                        {html.escape(letter)}
                    </span>

                    <span>
                        {clean_text(value)}
                    </span>

                </div>
                """
            )

            continue


        # ----------------------------------------------------
        # NUMBERED LIST
        # ----------------------------------------------------

        numbered_match = re.match(
            r"^(\d+)\.\s+(.*)",
            line
        )

        if numbered_match:

            number = numbered_match.group(
                1
            )

            value = numbered_match.group(
                2
            )

            # QUICK REVISION
            if current_special_open:

                if list_type != "revision":

                    close_list()

                    output.append(
                        "<ol class=\"revision-list\">"
                    )

                    list_type = "revision"

                output.append(
                    f"""
                    <li>
                        {clean_text(value)}
                    </li>
                    """
                )

                continue


            # FACTS
            if list_type != "facts":

                close_list()

                output.append(
                    "<ol class=\"facts-list\">"
                )

                list_type = "facts"

            output.append(
                f"""
                <li>
                    {clean_text(value)}
                </li>
                """
            )

            continue


        # ----------------------------------------------------
        # BULLET LIST
        # ----------------------------------------------------

        bullet_match = re.match(
            r"^[-*]\s+(.*)",
            line
        )

        if bullet_match:

            value = bullet_match.group(
                1
            )

            if list_type != "summary":

                close_list()

                output.append(
                    "<ul class=\"summary-list\">"
                )

                list_type = "summary"

            output.append(
                f"""
                <li>
                    <span class="summary-check">
                        ✓
                    </span>

                    <span>
                        {clean_text(value)}
                    </span>
                </li>
                """
            )

            continue


        # ----------------------------------------------------
        # HORIZONTAL RULE
        # ----------------------------------------------------

        if line.startswith("---"):

            close_list()

            continue


        # ----------------------------------------------------
        # RAW URL
        # ----------------------------------------------------

        raw_url = extract_link(
            line
        )

        if raw_url and line == raw_url:

            if pending_source_url:

                current_source_url = raw_url

                pending_source_url = False

                close_source_box()

                continue

            if pending_source_name:

                current_source_url = raw_url

                pending_source_name = False

                close_source_box()

                continue

            continue


        # ----------------------------------------------------
        # NORMAL TEXT
        # ----------------------------------------------------

        close_list()

        cleaned = remove_markdown_link(
            line
        )

        cleaned = cleaned.strip()

        if not cleaned:

            continue


        output.append(
            f"""
            <p>
                {clean_text(cleaned)}
            </p>
            """
        )


    # ========================================================
    # FINAL CLOSE
    # ========================================================

    close_list()

    close_source_box()

    close_topic()

    close_special()


    return "\n".join(
        output
    )


# ============================================================
# 10. GENERATE EMAIL CONTENT
# ============================================================

email_content = build_html(
    briefing
)


# ============================================================
# 11. BEAUTIFUL HTML EMAIL
# ============================================================

html_email = f"""
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>
    UPSC Daily Current Affairs
</title>


<style>

/* ==========================================================
   GENERAL
   ========================================================== */

body {{
    margin: 0;
    padding: 0;

    background: #eef2f7;

    font-family:
        Arial,
        Helvetica,
        sans-serif;

    color: #1e293b;

    line-height: 1.6;
}}


/* ==========================================================
   MAIN CONTAINER
   ========================================================== */

.container {{
    width: 100%;
    max-width: 760px;

    margin: 30px auto;

    background: #ffffff;

    border-radius: 16px;

    overflow: hidden;

    box-shadow:
        0 6px 25px
        rgba(15, 23, 42, 0.10);
}}


/* ==========================================================
   HEADER
   ========================================================== */

.header {{
    background:
        linear-gradient(
            135deg,
            #172554,
            #1e3a8a
        );

    color: #ffffff;

    padding: 36px 25px;

    text-align: center;
}}

.header h1 {{
    margin: 0;

    font-size: 28px;

    line-height: 1.3;
}}

.header-subtitle {{
    margin-top: 10px;

    font-size: 15px;

    opacity: 0.90;
}}

.header-date {{
    margin-top: 14px;

    display: inline-block;

    padding: 6px 12px;

    border-radius: 20px;

    background:
        rgba(255,255,255,0.12);

    font-size: 13px;
}}


/* ==========================================================
   CONTENT
   ========================================================== */

.content {{
    padding: 28px;
}}


/* ==========================================================
   TOPIC CARD
   ========================================================== */

.topic-card {{
    margin-bottom: 24px;

    border:
        1px solid #e2e8f0;

    border-radius: 14px;

    overflow: hidden;

    background: #ffffff;

    box-shadow:
        0 3px 12px
        rgba(15, 23, 42, 0.05);
}}

.topic-title {{
    padding: 20px 22px;

    background: #f8fafc;

    border-bottom:
        1px solid #e2e8f0;

    color: #172554;

    font-size: 20px;

    font-weight: 700;

    line-height: 1.4;
}}

.topic-body {{
    padding: 20px 22px;
}}


/* ==========================================================
   BADGES
   ========================================================== */

.badge {{
    display: inline-block;

    margin:
        0 7px 12px 0;

    padding:
        6px 11px;

    border-radius: 20px;

    font-size: 12px;

    font-weight: 700;
}}

.category {{
    background: #e0f2fe;

    color: #075985;
}}

.relevance {{
    background: #fef3c7;

    color: #92400e;
}}

.gs {{
    background: #ede9fe;

    color: #5b21b6;
}}


/* ==========================================================
   SECTION HEADINGS
   ========================================================== */

.section-heading {{
    margin-top: 20px;

    margin-bottom: 8px;

    color: #334155;

    font-size: 13px;

    font-weight: 800;

    letter-spacing: 0.5px;

    text-transform: uppercase;
}}


/* ==========================================================
   PARAGRAPHS
   ========================================================== */

p {{
    margin:
        7px 0 13px;

    font-size: 15px;

    line-height: 1.75;

    color: #334155;
}}

strong {{
    color: #0f172a;
}}


/* ==========================================================
   QUICK SUMMARY
   ========================================================== */

.summary-list {{
    list-style: none;

    margin:
        8px 0 18px;

    padding-left: 0;
}}

.summary-list li {{
    display: flex;

    gap: 9px;

    margin-bottom: 9px;

    padding:
        9px 12px;

    background: #f8fafc;

    border-left:
        3px solid #2563eb;

    border-radius: 6px;

    font-size: 14px;

    line-height: 1.6;
}}

.summary-check {{
    flex-shrink: 0;

    font-weight: 800;

    color: #2563eb;
}}


/* ==========================================================
   FACTS
   ========================================================== */

.facts-list {{
    margin:
        8px 0 15px;

    padding-left: 26px;
}}

.facts-list li {{
    margin-bottom: 10px;

    padding-left: 4px;

    line-height: 1.65;

    font-size: 14px;
}}


/* ==========================================================
   REVISION
   ========================================================== */

.revision-list {{
    margin:
        8px 0 15px;

    padding-left: 28px;
}}

.revision-list li {{
    margin-bottom: 11px;

    font-size: 14px;

    line-height: 1.65;
}}


/* ==========================================================
   SOURCE
   ========================================================== */

.source-box {{
    margin-top: 20px;

    padding: 16px;

    border:
        1px solid #dbeafe;

    border-radius: 10px;

    background: #f8fafc;
}}

.source-label {{
    color: #334155;

    font-size: 12px;

    font-weight: 800;

    text-transform: uppercase;
}}

.source-name {{
    margin:
        5px 0 12px;

    color: #475569;

    font-size: 13px;

    line-height: 1.5;
}}

.source-button {{
    display: inline-block;

    padding:
        8px 14px;

    background: #1d4ed8;

    color: #ffffff !important;

    border-radius: 7px;

    text-decoration: none;

    font-size: 12px;

    font-weight: 700;
}}


/* ==========================================================
   ARTICLE TITLE
   ========================================================== */

.article-title {{
    margin-top: 12px;

    color: #64748b;

    font-size: 12px;
}}


/* ==========================================================
   MCQ QUESTION
   ========================================================== */

.mcq-question {{
    margin:
        10px 0 12px;

    font-size: 14px;

    line-height: 1.7;

    color: #334155;
}}


/* ==========================================================
   MCQ OPTIONS
   ========================================================== */

.option {{
    display: flex;

    align-items: flex-start;

    gap: 10px;

    margin:
        7px 0;

    padding:
        10px 12px;

    border:
        1px solid #e2e8f0;

    border-radius: 8px;

    background: #f8fafc;

    font-size: 14px;
}}

.option-letter {{
    flex-shrink: 0;

    width: 24px;

    height: 24px;

    display: flex;

    align-items: center;

    justify-content: center;

    border-radius: 50%;

    background: #e2e8f0;

    color: #334155;

    font-weight: 800;

    font-size: 12px;
}}


/* ==========================================================
   MCQ TITLE
   ========================================================== */

.mcq-title {{
    margin-top: 22px;

    margin-bottom: 10px;

    color: #4c1d95;

    font-size: 16px;

    font-weight: 800;
}}


/* ==========================================================
   ANSWER
   ========================================================== */

.answer-box {{
    margin-top: 13px;

    padding:
        12px 14px;

    background: #ecfdf5;

    border-left:
        4px solid #10b981;

    border-radius: 7px;

    color: #065f46;

    font-size: 14px;
}}


/* ==========================================================
   EXPLANATION
   ========================================================== */

.explanation {{
    margin-top: 8px;

    padding:
        10px 12px;

    background: #f8fafc;

    border-radius: 7px;

    color: #475569;

    font-size: 13px;

    line-height: 1.6;
}}


/* ==========================================================
   SPECIAL CARDS
   ========================================================== */

.special-card {{
    margin-top: 28px;

    margin-bottom: 24px;

    padding: 22px;

    border-radius: 14px;
}}

.special-title {{
    margin-bottom: 18px;

    font-size: 20px;

    font-weight: 800;
}}

.special-body {{
    font-size: 14px;
}}


/* ==========================================================
   REVISION CARD
   ========================================================== */

.revision-card {{
    background: #eff6ff;

    border:
        1px solid #bfdbfe;
}}

.revision-card .special-title {{
    color: #1e3a8a;
}}


/* ==========================================================
   MCQ CARD
   ========================================================== */

.mcq-card {{
    background: #faf5ff;

    border:
        1px solid #ddd6fe;
}}

.mcq-card .special-title {{
    color: #5b21b6;
}}


/* ==========================================================
   MAINS CARD
   ========================================================== */

.mains-card {{
    background: #fff7ed;

    border:
        1px solid #fed7aa;
}}

.mains-card .special-title {{
    color: #9a3412;
}}


/* ==========================================================
   FOOTER
   ========================================================== */

.footer {{
    padding:
        22px 25px;

    background: #f8fafc;

    border-top:
        1px solid #e2e8f0;

    text-align: center;

    color: #64748b;

    font-size: 12px;

    line-height: 1.7;
}}

.footer strong {{
    color: #334155;
}}


/* ==========================================================
   MOBILE
   ========================================================== */

@media only screen and (max-width: 600px) {{

    body {{
        background: #ffffff;
    }}

    .container {{
        margin: 0;

        border-radius: 0;

        box-shadow: none;
    }}

    .header {{
        padding:
            28px 18px;
    }}

    .header h1 {{
        font-size: 23px;
    }}

    .content {{
        padding: 16px;
    }}

    .topic-title {{
        padding:
            17px;

        font-size: 18px;
    }}

    .topic-body {{
        padding:
            17px;
    }}

    .special-card {{
        padding:
            17px;
    }}

    p {{
        font-size: 14px;
    }}

}}

</style>

</head>


<body>

<div class="container">


    <!-- HEADER -->

    <div class="header">

        <h1>
            🇮🇳 UPSC Daily Current Affairs
        </h1>

        <div class="header-subtitle">
            AI-powered Civil Services Briefing
        </div>

        <div class="header-date">
            {today}
        </div>

    </div>


    <!-- CONTENT -->

    <div class="content">

        {email_content}

    </div>


    <!-- FOOTER -->

    <div class="footer">

        <strong>
            UPSC AI News Agent
        </strong>

        <br>

        Generated automatically from current news.

        <br><br>

        ⚠️ Always verify important facts with
        authoritative sources before using them
        in an examination.

    </div>


</div>

</body>

</html>
"""


# ============================================================
# 12. SEND EMAIL
# ============================================================

sender = os.environ[
    "GMAIL_USERNAME"
]

app_password = os.environ[
    "GMAIL_APP_PASSWORD"
]

recipient = sender


message = MIMEMultipart(
    "alternative"
)


message["Subject"] = (
    "🇮🇳 UPSC Daily Current Affairs - AI Briefing"
)

message["From"] = sender

message["To"] = recipient


# ------------------------------------------------------------
# PLAIN TEXT FALLBACK
# ------------------------------------------------------------

message.attach(
    MIMEText(
        briefing,
        "plain",
        "utf-8"
    )
)


# ------------------------------------------------------------
# HTML EMAIL
# ------------------------------------------------------------

message.attach(
    MIMEText(
        html_email,
        "html",
        "utf-8"
    )
)


# ============================================================
# 13. SEND THROUGH GMAIL SMTP
# ============================================================

print(
    "\nSending email..."
)


with smtplib.SMTP(
    "smtp.gmail.com",
    587
) as server:

    server.starttls()

    server.login(
        sender,
        app_password
    )

    server.sendmail(
        sender,
        recipient,
        message.as_string()
    )


print(
    "\n===================================="
)

print(
    "EMAIL SENT SUCCESSFULLY"
)

print(
    "===================================="
)
