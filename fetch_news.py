#!/usr/bin/env python3
"""
每日前沿消息爬虫
从 Hacker News、GitHub Trending、Product Hunt、arXiv 爬取数据
使用 Claude AI 筛选最有价值的 3-5 条消息
"""

import json
import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False


def fetch_hacker_news(limit=10):
    """获取 Hacker News Top Stories"""
    try:
        # 获取 top stories IDs
        url = "https://hacker-news.firebaseio.com/v0/topstories.json"
        response = requests.get(url, timeout=10)
        story_ids = response.json()[:limit]

        items = []
        for story_id in story_ids:
            story_url = f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
            story = requests.get(story_url, timeout=10).json()
            if story:
                items.append({
                    "title": story.get("title", ""),
                    "url": story.get("url", f"https://news.ycombinator.com/item?id={story_id}"),
                    "score": story.get("score", 0),
                    "source": "Hacker News",
                    "category": "tech"
                })
        return items
    except Exception as e:
        print(f"Hacker News error: {e}")
        return []


def fetch_github_trending():
    """获取 GitHub Trending"""
    try:
        url = "https://github.com/trending"
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")

        items = []
        repos = soup.select("article.Box-row")[:8]
        for repo in repos:
            name_elem = repo.select_one("h2 a")
            if name_elem:
                name = name_elem.get_text(strip=True).replace("\n", "").replace(" ", "")
                link = "https://github.com" + name_elem.get("href", "")
                desc_elem = repo.select_one("p")
                desc = desc_elem.get_text(strip=True) if desc_elem else ""
                items.append({
                    "title": name,
                    "url": link,
                    "summary": desc[:150] if desc else "GitHub热门项目",
                    "source": "GitHub",
                    "category": "dev"
                })
        return items
    except Exception as e:
        print(f"GitHub Trending error: {e}")
        return []


def fetch_producthunt():
    """获取 Product Hunt RSS"""
    try:
        url = "https://www.producthunt.com/feed"
        response = requests.get(url, timeout=10)
        root = ET.fromstring(response.text)
        items = []
        for entry in root.findall(".//entry")[:8]:
            title = entry.findtext("title", "")
            link = entry.findtext("link", "")
            summary = entry.findtext("summary", "")
            if summary:
                summary = summary[:150]
            else:
                summary = "新产品发布"
            items.append({
                "title": title,
                "url": link,
                "summary": summary,
                "source": "Product Hunt",
                "category": "startup"
            })
        return items
    except Exception as e:
        print(f"Product Hunt error: {e}")
        return []


def fetch_arxiv_ai():
    """获取 arXiv AI 最新论文"""
    try:
        url = "http://export.arxiv.org/api/query?search_query=cat:cs.AI&start=0&max_results=10&sortBy=submittedDate&sortOrder=descending"
        response = requests.get(url, timeout=15)
        root = ET.fromstring(response.text)

        # arXiv uses Atom namespace
        ns = {'atom': 'http://www.w3.org/2005/Atom'}

        items = []
        for entry in root.findall('atom:entry', ns)[:8]:
            title = entry.findtext('atom:title', '', ns).replace('\n', ' ').strip()
            link = entry.find('atom:id', ns)
            link = link.text if link is not None else ''
            summary = entry.findtext('atom:summary', '', ns).replace('\n', ' ').strip()[:200] + '...'

            items.append({
                "title": title,
                "url": link,
                "summary": summary,
                "source": "arXiv",
                "category": "ai"
            })
        return items
    except Exception as e:
        print(f"arXiv error: {e}")
        return []


def fetch_douyin_hot():
    """获取抖音热榜 - 直接抓取网页"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X_10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    # 尝试抓取沸点页面（不需要登录）
    try:
        url = "https://hot.duanzhihua.com/api/douyin"
        response = requests.get(url, headers=headers, timeout=15, verify=False)
        data = response.json()

        items = []
        for item in data[:10]:
            items.append({
                "title": item.get("title", item.get("name", "")),
                "url": item.get("url", ""),
                "summary": f"热度: {item.get('hot', item.get('view', '未知'))}",
                "source": "抖音热榜",
                "category": "hot"
            })
        return items
    except Exception as e:
        print(f"Hot list error: {e}")
        # 最后备用：生成一些静态热点提示
        return [{
            "title": "今日热榜数据暂时无法获取",
            "url": "https://www.douyin.com",
            "summary": "API服务不稳定，请稍后再试",
            "source": "系统提示",
            "category": "hot"
        }]


def ai_select_news(candidates):
    """使用 Claude AI 筛选最有价值的消息"""
    if not candidates:
        return []

    if not HAS_ANTHROPIC:
        print("anthropic not installed, returning top 5")
        return candidates[:5]

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY not set, returning top 5")
        return candidates[:5]

    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""你是一个科技资讯编辑。请从以下候选消息中筛选出 5-8 条最有价值、最前沿的消息。

候选消息:
{json.dumps(candidates, ensure_ascii=False, indent=2)}

筛选标准:
1. 选择对读者最有价值的内容
2. 优先选择突破性、创新性的消息
3. 保持领域多样性（AI、开发、创业、科技、热点）
4. 抖音热榜选择2-3条最有意思的
5. **标题和摘要必须翻译成中文**

返回 JSON 格式:
{{
  "selected": [
    {{
      "title": "中文标题",
      "url": "原链接",
      "summary": "中文摘要（30字以内）",
      "source": "来源",
      "category": "分类"
    }}
  ]
}}

只返回 JSON，不要其他内容。"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        result = json.loads(message.content[0].text)
        return result.get("selected", [])
    except Exception as e:
        print(f"AI selection error: {e}")
        # 降级: 返回前5条
        return candidates[:5]


def generate_html(news_items):
    """生成 HTML 页面"""
    env = Environment(loader=FileSystemLoader("."))
    template = env.get_template("template.html")

    html_content = template.render(
        date=datetime.now().strftime("%Y年%m月%d日"),
        news=news_items
    )

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("Generated index.html")


def main():
    print("Fetching news...")
    all_news = []

    # 爬取各来源
    all_news.extend(fetch_hacker_news())
    all_news.extend(fetch_github_trending())
    all_news.extend(fetch_producthunt())
    all_news.extend(fetch_arxiv_ai())
    all_news.extend(fetch_douyin_hot())

    print(f"Total candidates: {len(all_news)}")

    # AI 筛选
    print("AI selecting...")
    selected = ai_select_news(all_news)
    print(f"Selected: {len(selected)} items")

    # 生成 HTML
    generate_html(selected)
    print("Done!")


if __name__ == "__main__":
    main()
