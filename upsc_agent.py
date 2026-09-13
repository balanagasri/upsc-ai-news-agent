import os
import json
import base64
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
from email.utils import parsedate_to_datetime


# ============================================================
# 1. FETCH NEWS
# ============================================================

# This version uses THREE freshness safeguards:
# 1) Google News query freshness (when:1d / when:2d)
# 2) RSS publication timestamp check
# 3) A Gemini screening step that rejects articles whose underlying
#    event/development is clearly old or merely a background/repost story.

queries = [
    "India government policy when:1d",
    "India economy RBI when:1d",
    "Supreme Court India when:1d",
    "India environment climate when:1d",
    "India science technology when:1d",
    "India international relations when:1d",
    "India government schemes when:1d",
    "India polity governance when:1d",
    "India agriculture when:1d",
    "India internal security when:1d"
]

articles = []

# Keep the window deliberately tight. The final screening step is even stricter.
NOW_UTC = datetime.now(timezone.utc)
FRESHNESS_CUTOFF = NOW_UTC - timedelta(hours=36)


def strip_html(text):
    """Turn RSS HTML into readable plain text."""
    if not text:
        return ""

    text = html.unescape(text)
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fetch_article_page(url):
    """Best-effort extraction of publisher page text and publication date.

    This is deliberately non-fatal: some publishers block automated requests.
    In that case RSS data is still available and Gemini screening remains active.
    """
    if not url:
        return "", None

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/131 Safari/537.36"
            ),
            "Accept-Language": "en-IN,en;q=0.9"
        }
    )

    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            raw = response.read(500000).decode("utf-8", errors="ignore")

        # Prefer an explicit article publication date. Never use dateModified
        # as proof that an old article is new.
        published_candidates = []

        patterns = [
            r'"datePublished"\s*:\s*"([^"]+)"',
            r'"datePublished"\s*:\s*\{[^}]*"@value"\s*:\s*"([^"]+)"',
            r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+name=["\']date["\'][^>]+content=["\']([^"\']+)'
        ]

        for pattern in patterns:
            published_candidates.extend(re.findall(pattern, raw, re.IGNORECASE))

        page_published_at = None

        for candidate in published_candidates:
            candidate = html.unescape(candidate).strip()
            try:
                parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                page_published_at = parsed.astimezone(timezone.utc)
                break
            except Exception:
                try:
                    parsed = parsedate_to_datetime(candidate)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    page_published_at = parsed.astimezone(timezone.utc)
                    break
                except Exception:
                    continue

        text = strip_html(raw)

        # Keep enough article text for event-date screening without making the
        # final Gemini prompt unnecessarily huge.
        text = text[:5000]
        return text, page_published_at

    except Exception as e:
        print(f"Could not fetch publisher page: {e}")
        return "", None


for query in queries:

    encoded_query = urllib.parse.quote(query)

    rss_url = (
        "https://news.google.com/rss/search?"
        f"q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
    )

    try:
        with urllib.request.urlopen(rss_url, timeout=20) as response:
            xml_data = response.read()

        root = ET.fromstring(xml_data)

        for item in root.findall(".//item")[:12]:

            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            description = strip_html(item.findtext("description", ""))
            pub_date_text = item.findtext("pubDate", "")

            if not title or not link or not pub_date_text:
                continue

            try:
                published_at = parsedate_to_datetime(pub_date_text)
                if published_at.tzinfo is None:
                    published_at = published_at.replace(tzinfo=timezone.utc)
                published_at = published_at.astimezone(timezone.utc)
            except Exception:
                print(f"Skipping article with invalid publication date: {title}")
                continue

            if published_at < FRESHNESS_CUTOFF:
                print(
                    f"Skipping old RSS article: {title} "
                    f"({published_at.isoformat()})"
                )
                continue

            source_element = item.find("source")
            source_name = (
                source_element.text.strip()
                if source_element is not None and source_element.text
                else ""
            )

            # Fetch the publisher page where possible. If its explicit
            # datePublished is old, reject the item even if Google News
            # recently surfaced it.
            page_text, page_published_at = fetch_article_page(link)

            if page_published_at is not None and page_published_at < FRESHNESS_CUTOFF:
                print(
                    f"Skipping old publisher article: {title} "
                    f"(datePublished={page_published_at.isoformat()})"
                )
                continue

            articles.append(
                {
                    "title": title,
                    "link": link,
                    "description": description,
                    "source": source_name,
                    "published_at": published_at,
                    "page_published_at": page_published_at,
                    "page_text": page_text
                }
            )

    except Exception as e:
        print(f"Could not fetch '{query}': {e}")


# ============================================================
# 2. SORT + REMOVE DUPLICATES
# ============================================================

articles.sort(
    key=lambda article: article["published_at"],
    reverse=True
)

unique_articles = {}

for article in articles:
    title_key = re.sub(r"[^a-z0-9]+", " ", article["title"].lower()).strip()
    if title_key and title_key not in unique_articles:
        unique_articles[title_key] = article

articles = list(unique_articles.values())

print(
    f"Collected {len(articles)} fresh candidate articles from the last 36 hours."
)

if not articles:
    raise Exception("No recent news articles were collected.")


# ============================================================
# 3. REDUCE CANDIDATES BEFORE GEMINI
# ============================================================

# The RSS and publisher publication-date checks above are deterministic.
# Keep a manageable number of the newest candidates for the single Gemini
# call below. Gemini will perform the final EVENT freshness check as part of
# topic selection.
articles = articles[:50]

print(
    f"Sending {len(articles)} recent candidates to Gemini for strict UPSC selection."
)

if not articles:
    raise Exception("No recent news candidates remain.")


# ============================================================
# 4. PREPARE NEWS FOR FINAL GEMINI BRIEFING
# ============================================================

news_text = ""

for i, article in enumerate(articles[:20], 1):
    news_text += (
        f"\nARTICLE {i}\n"
        f"TITLE: {article['title']}\n"
        f"SOURCE NAME: {article['source']}\n"
        f"RSS PUBLISHED AT (UTC): {article['published_at'].isoformat()}\n"
        f"PUBLISHER DATEPUBLISHED (UTC): "
        f"{article['page_published_at'].isoformat() if article['page_published_at'] else 'Not available'}\n"
        f"DESCRIPTION: {article['description']}\n"
        f"PUBLISHER ARTICLE TEXT: {article['page_text'][:4500]}\n"
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

3. The supplied articles have already passed a 48-hour publication
freshness check. Treat the supplied publication timestamp as the
article publication time, not automatically as the event date.

4. If an event happened earlier but is newly reported, clearly
distinguish the event date from the publication date when supported.

5. Do not claim that a government action, Supreme Court order,
RBI decision, policy, scheme, statistic or international event
happened unless the supplied article supports it.

6. Do not invent dates, numbers, statistics, names, locations,
government departments, court orders, laws, schemes, reports,
rankings, organizations or policy details.

7. If an important fact cannot be established from the supplied
material, write "Requires verification." Do not guess.

8. Clearly distinguish between:
   - what actually happened,
   - what a person or organization said,
   - what is proposed or expected,
   - and what is analysis or opinion.

9. Never convert a proposal, recommendation, discussion, criticism,
prediction or statement into a confirmed government decision or
implemented policy.

10. For Supreme Court or other court-related news, do not invent
case names, judgment details, constitutional provisions, legal
principles or court directions unless supported by the article.

11. For RBI, economy and government-policy news, do not invent
percentages, dates, monetary values, policy changes, decisions or
economic indicators.

12. For international relations, do not assume that a meeting,
agreement, treaty, conflict, visit or diplomatic decision occurred
unless supported by the supplied article.

13. For environment, climate, biodiversity and science topics, do not
invent species, locations, measurements, scientific findings,
project details, classifications or government actions.

14. For UPSC Prelims Facts, include only facts directly supported by
the supplied articles. If there are not enough verified facts,
prefer simpler supported facts rather than guessing.

15. For MCQs, every correct answer and explanation must be directly
supported by the supplied current-affairs material or by a clearly
stated concept contained in that material. Never create a question
whose answer depends on an unsupported factual claim.

16. For Quick Revision Points, include only information already
established in the selected topics. Do not introduce new facts.

17. For the Mains Angle and Mains Practice Question, base the issue
on the supplied article. Do not introduce an unrelated factual claim.

18. Do not confuse a news organization's reporting or opinion with
an official government source. If an article reports what someone
said, attribute it clearly.

19. Use the supplied source URL exactly. Do not change, shorten,
invent or replace the URL.

20. If the supplied article is insufficient to establish a claim,
say "Requires verification." rather than completing the claim from
memory.

21. Accuracy is more important than completeness. It is better to
omit a detail than provide an uncertain or fabricated detail.

22. Do not manufacture information merely to fill a required section.
If a section cannot be supported, keep it concise and state
"Requires verification." where appropriate.

23. Select topics based on UPSC importance, not simply because an
article is available.

24. Before finalizing each topic, internally check every factual
claim against the supplied article(s). Remove unsupported claims.

========================================================================================================================
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
STRICT CURRENT-AFFAIRS SELECTION
============================================================

The candidate articles were published recently, but some may discuss older
events. This is the most important selection rule.

For every candidate, inspect the title, RSS description, and publisher text.
Select it ONLY if the supplied evidence indicates that the underlying
development itself occurred, changed, was announced, decided, reported, or
materially advanced within the last 48 hours.

REJECT a candidate if it is:
- a newly published article about an old event;
- a background or explainer article;
- an old scheme/policy/court matter being discussed again without a new action;
- a retrospective, anniversary, profile, opinion, or analysis without a new
  substantive development;
- a story whose event date cannot be established from the supplied evidence;
- a duplicate/rewrite that adds no new development.

When uncertain, REJECT it. Do not use outside knowledge to make an old event
look current. Do not invent an event date.

If the article reports a continuing story, keep it only when the supplied text
shows a substantive development within the last 48 hours.

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

The articles below passed a deterministic publication-date freshness check:
- Google News search used when:1d.
- RSS publication timestamp is within the last 36 hours.
- When available, publisher datePublished is also within the last 36 hours.

IMPORTANT: A recent publication date does NOT prove that the underlying
event is recent. You must independently judge event freshness from the
supplied article text. Reject recycled/background/old-event stories.

{news_text}
"""


# ============================================================
# 5. CALL GEMINI WITH RETRIES
# ============================================================

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY is not configured in GitHub Secrets.")

# Stable Gemini model used by this project.
GEMINI_MODEL = "gemini-3.5-flash"
gemini_url = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)


# Gemini can occasionally return 503 Service Unavailable. Retry transient
# failures instead of immediately failing the daily workflow.

def call_gemini_with_retry(request, attempts=4, timeout=120):

    delays = [5, 15, 30, 60]

    for attempt in range(attempts):

        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout
            ) as response:
                return json.loads(
                    response.read().decode("utf-8")
                )

        except urllib.error.HTTPError as e:

            error_body = e.read().decode("utf-8", errors="ignore")

            print(
                f"Gemini API HTTP {e.code} on attempt "
                f"{attempt + 1}/{attempts}."
            )

            if e.code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
                import time
                delay = delays[attempt]
                print(f"Transient Gemini error. Retrying in {delay} seconds...")
                time.sleep(delay)
                continue

            print(error_body[:2000])
            raise

        except (urllib.error.URLError, TimeoutError) as e:

            print(
                f"Gemini connection error on attempt "
                f"{attempt + 1}/{attempts}: {e}"
            )

            if attempt < attempts - 1:
                import time
                delay = delays[attempt]
                print(f"Transient connection error. Retrying in {delay} seconds...")
                time.sleep(delay)
                continue

            raise


request_body = {
    "contents": [
        {
            "parts": [
                {
                    "text": prompt
                }
            ]
        }
    ],
    "generationConfig": {
        "temperature": 0.1
    }
}

request = urllib.request.Request(
    gemini_url,
    data=json.dumps(request_body).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
        "x-goog-api-key": api_key
    },
    method="POST"
)

result = call_gemini_with_retry(request)



# ============================================================
# GOOGLE NEWS URL RESOLVER
# ============================================================

def _try_decode_legacy_google_news_url(article_id):
    """Decode older Google News RSS article IDs when they contain
    the original URL directly."""
    try:
        padded = article_id + ("=" * (-len(article_id) % 4))
        raw = base64.urlsafe_b64decode(padded)
        if raw.startswith(b"\x08\x13\x22"):
            raw = raw[3:]

        if raw.endswith(b"\xd2\x01\x00"):
            raw = raw[:-3]

        if not raw:
            return ""

        first = raw[0]
        if first < 0x80:
            length = first
            start = 1
        elif len(raw) >= 2:
            length = (first & 0x7F) | (raw[1] << 7)
            start = 2
        else:
            return ""

        candidate = raw[start:start + length].decode("utf-8", errors="ignore").strip()

        if candidate.startswith(("http://", "https://")):
            return candidate

    except Exception:
        pass

    return ""


def resolve_google_news_url(url):
    """Resolve a Google News RSS article URL to the publisher URL.

    Google News RSS now commonly returns signed intermediate URLs rather
    than direct publisher links. We first try the older embedded-URL
    format, then Google's current garturl/batchexecute endpoint.
    If resolution fails, the original URL is returned so the newsletter
    can still be sent.
    """
    try:
        parsed = urllib.parse.urlparse(url)

        if parsed.hostname not in {"news.google.com", "www.news.google.com"}:
            return url

        parts = [part for part in parsed.path.split("/") if part]
        if "articles" not in parts:
            return url

        article_id = parts[-1]

        legacy = _try_decode_legacy_google_news_url(article_id)
        if legacy and "news.google.com" not in urllib.parse.urlparse(legacy).netloc:
            return legacy

        # Current Google News resolver endpoint.
        payload_string = (
            '[[["Fbv4je","[\\\"garturlreq\\\",'
            '[[\\\"en-US\\\",\\\"IN\\\",'
            '[\\\"FINANCE_TOP_INDICES\\\",\\\"WEB_TEST_1_0_0\\\"],'
            'null,null,1,1,\\\"IN:en\\\",null,180,null,null,null,null,'
            'null,0,null,null,[1608992183,723341000]],'
            '\\\"en-US\\\",\\\"IN\\\",1,[2,3,4,8],1,0,\\\"655000234\\\",'
            '0,0,null,0],\\\"'
            + article_id
            + '\\\"]",null,"generic"]]]'
        )

        body = "f.req=" + urllib.parse.quote(payload_string, safe="")
        request = urllib.request.Request(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute?rpcids=Fbv4je",
            data=body.encode("utf-8"),
            headers={
                "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
                "Referer": "https://news.google.com/",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/131 Safari/537.36"
                ),
            },
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=15) as response:
            response_text = response.read().decode("utf-8", errors="ignore")

        marker = '[\\"garturlres\\",\\"'
        if marker in response_text:
            start = response_text.index(marker) + len(marker)
            remainder = response_text[start:]
            end_marker = '\\",'
            if end_marker in remainder:
                resolved = remainder.split(end_marker, 1)[0]
                resolved = resolved.replace("\\/", "/").replace('\\"', '"')

                if resolved.startswith(("http://", "https://")):
                    host = urllib.parse.urlparse(resolved).hostname or ""
                    if host not in {"news.google.com", "www.news.google.com"}:
                        return resolved

    except Exception as e:
        print(f"Could not resolve Google News URL: {e}")

    return url


def resolve_google_news_links_in_text(text):
    """Replace Google News RSS links in Gemini output with publisher URLs."""
    pattern = re.compile(
        r"https://news\.google\.com/(?:rss/)?articles/[A-Za-z0-9_-]+(?:\?[^\s)\]>]+)?"
    )

    cache = {}

    def replace(match):
        original = match.group(0)
        if original not in cache:
            cache[original] = resolve_google_news_url(original)
        return cache[original]

    return pattern.sub(replace, text)


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


# Replace Google News redirect links with direct publisher URLs where possible.
# This happens after Gemini selection, so only the few final article links need
# to be resolved.
briefing = resolve_google_news_links_in_text(briefing)


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
