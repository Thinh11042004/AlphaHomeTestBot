from app.models.article import Article
from app.services.cleaner import HtmlMarkdownCleaner


def test_cleaner_removes_nav_and_preserves_headings_code_and_links():
    article = Article(
        id="1",
        title="Sample Article",
        html_url="https://support.optisigns.com/hc/en-us/articles/1",
        body_html="""
        <nav>Remove me</nav>
        <h2>Setup</h2>
        <p>Open <a href="https://support.optisigns.com/hc/en-us/articles/2-Other">other</a>.</p>
        <pre><code>print("ok")</code></pre>
        <footer>Remove footer</footer>
        """,
        updated_at="2026-01-01T00:00:00Z",
        locale="en-us",
        slug="sample-article",
    )

    markdown = HtmlMarkdownCleaner("https://support.optisigns.com").to_markdown(article)

    assert "Remove me" not in markdown
    assert "Remove footer" not in markdown
    assert "## Setup" in markdown
    assert "Article URL: https://support.optisigns.com/hc/en-us/articles/1" in markdown
    assert "](/hc/en-us/articles/2-Other)" in markdown
    assert "print(\"ok\")" in markdown
