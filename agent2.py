import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from strands import Agent
from strands.models import BedrockModel
import re
import xml.etree.ElementTree as ET

# === Step 1: Claude (via Bedrock) 設定 ===
model = BedrockModel(
    model_id="anthropic.claude-3-5-sonnet-20240620-v1:0",
    anthropic_version="bedrock-2023-05-31"
)
agent = Agent(model=model)

# === Step 2: AWS RSS Feed から1週間分取得 ===
def scrape_aws_news_rss():
    """AWS What's NewのRSSフィードから記事を取得"""
    rss_url = "https://aws.amazon.com/new/feed/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        res = requests.get(rss_url, headers=headers, timeout=10)
        res.raise_for_status()
    except requests.RequestException as e:
        print(f"エラー: RSSフィードの取得に失敗しました - {e}")
        return ""
    
    try:
        root = ET.fromstring(res.content)
    except ET.ParseError as e:
        print(f"エラー: XMLの解析に失敗しました - {e}")
        return ""
    
    today = datetime.now()
    one_week_ago = today - timedelta(days=7)
    news = []
    
    print(f"日付フィルター: {one_week_ago.strftime('%Y-%m-%d')} 以降の記事を抽出")
    
    # RSS itemsを取得
    items = root.findall('.//item')
    print(f"RSSから {len(items)} 件のアイテムを発見")
    
    for i, item in enumerate(items):
        title_elem = item.find('title')
        pub_date_elem = item.find('pubDate')
        desc_elem = item.find('description')
        
        if title_elem is None:
            continue
            
        title = title_elem.text.strip() if title_elem.text else ""
        
        # 日付の解析
        parsed_date = None
        if pub_date_elem is not None and pub_date_elem.text:
            pub_date_text = pub_date_elem.text.strip()
            print(f"アイテム {i}: 日付テキスト = '{pub_date_text}'")
            
            # RFC 2822 形式の日付解析 (例: Thu, 06 Jun 2024 10:00:00 +0000)
            try:
                parsed_date = datetime.strptime(pub_date_text, "%a, %d %b %Y %H:%M:%S %z")
                parsed_date = parsed_date.replace(tzinfo=None)  # タイムゾーン情報を削除
            except ValueError:
                try:
                    parsed_date = datetime.strptime(pub_date_text, "%a, %d %b %Y %H:%M:%S GMT")
                except ValueError:
                    print(f"アイテム {i}: 日付の解析に失敗 '{pub_date_text}'")
                    continue
        else:
            print(f"アイテム {i}: 日付情報がありません")
            continue
        
        print(f"アイテム {i}: 解析された日付 = {parsed_date.strftime('%Y-%m-%d')}")
        
        # 1週間以内かチェック
        if parsed_date < one_week_ago:
            print(f"アイテム {i}: 1週間より古い記事のためスキップ")
            continue
        
        # 説明文の取得
        desc = ""
        if desc_elem is not None and desc_elem.text:
            desc = desc_elem.text.strip()
            # HTMLタグを削除
            desc = re.sub(r'<[^>]+>', '', desc)
            # 長い説明文は短縮
            if len(desc) > 200:
                desc = desc[:200] + "..."
        
        news_item = f"- [{parsed_date.strftime('%Y-%m-%d')}] {title}"
        if desc:
            news_item += f": {desc}"
        
        news.append(news_item)
        print(f"アイテム {i}: 追加しました - {title}")
    
    print(f"\n合計 {len(news)} 件の1週間以内の記事を取得しました")
    return "\n".join(news)

# === Step 2: AWS News Blog から1週間分取得 (フォールバック) ===
def scrape_aws_news():
    # AWS What's Newページは動的読み込みのため、AWS News Blogを使用
    url = "https://aws.amazon.com/blogs/aws/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
    except requests.RequestException as e:
        print(f"エラー: ページの取得に失敗しました - {e}")
        return ""
    
    soup = BeautifulSoup(res.text, "html.parser")
    
    # AWS News Blogのセレクターを試す
    possible_selectors = [
        "article",
        ".post",
        ".blog-post",
        ".entry",
        ".post-item",
        ".blog-item"
    ]
    
    items = []
    for selector in possible_selectors:
        items = soup.select(selector)
        if items:
            print(f"セレクター '{selector}' で {len(items)} 件のアイテムを発見")
            break
    
    if not items:
        print("アイテムが見つかりませんでした。HTML構造を確認します...")
        # デバッグ用: 実際のHTML構造を少し表示
        print("HTML構造のサンプル:")
        print(soup.prettify()[:2000])
        return ""

    today = datetime.now()
    one_week_ago = today - timedelta(days=7)
    news = []
    
    print(f"日付フィルター: {one_week_ago.strftime('%Y-%m-%d')} 以降の記事を抽出")

    for i, item in enumerate(items[:20]):  # 最初の20件をチェック
        # 日付の取得を複数のパターンで試行
        date_element = None
        date_selectors = [
            "time",
            ".date",
            ".publish-date",
            ".entry-date",
            ".post-date",
            ".meta-date",
            "[datetime]"
        ]
        
        for date_sel in date_selectors:
            date_element = item.select_one(date_sel)
            if date_element:
                break
        
        # タイトルの取得
        title_element = None
        title_selectors = [
            "h1",
            "h2",
            "h3",
            ".title",
            ".entry-title",
            ".post-title",
            "a[href*='/blogs/']"
        ]
        
        for title_sel in title_selectors:
            title_element = item.select_one(title_sel)
            if title_element and title_element.text.strip():
                break
        
        if not title_element:
            print(f"アイテム {i}: タイトルが見つかりません")
            continue

        # 日付の処理
        parsed_date = None
        if date_element:
            # datetime属性がある場合
            if date_element.get('datetime'):
                date_text = date_element.get('datetime')
            else:
                date_text = date_element.text.strip()
            
            print(f"アイテム {i}: 日付テキスト = '{date_text}'")
            
            # 日付解析の複数パターン対応
            date_patterns = [
                "%Y-%m-%dT%H:%M:%S%z",    # ISO format with timezone
                "%Y-%m-%dT%H:%M:%S",      # ISO format
                "%Y-%m-%d",               # 2024-06-11
                "%B %d, %Y",              # June 11, 2024
                "%d %B %Y",               # 11 June 2024
                "%m/%d/%Y",               # 06/11/2024
                "%Y.%m.%d",               # 2024.06.11
            ]
            
            # 日付テキストから数字部分を抽出
            date_match = re.search(r'(\d{4})[/-.](\d{1,2})[/-.](\d{1,2})', date_text)
            if date_match:
                year, month, day = date_match.groups()
                try:
                    parsed_date = datetime(int(year), int(month), int(day))
                except ValueError:
                    pass
            
            if not parsed_date:
                # 他のパターンも試行
                for pattern in date_patterns:
                    try:
                        parsed_date = datetime.strptime(date_text.split('T')[0], pattern.split('T')[0])
                        break
                    except ValueError:
                        continue
        
        # 日付が取得できない場合は、記事の順序から最近のものと仮定
        if not parsed_date:
            if i < 5:  # 最初の5件は最近の記事と仮定
                parsed_date = today
                print(f"アイテム {i}: 日付不明のため最新記事と仮定")
            else:
                print(f"アイテム {i}: 日付の解析に失敗、スキップ")
                continue
        else:
            print(f"アイテム {i}: 解析された日付 = {parsed_date.strftime('%Y-%m-%d')}")
        
        # 1週間以内かチェック
        if parsed_date < one_week_ago:
            print(f"アイテム {i}: 1週間より古い記事のためスキップ")
            continue

        title = title_element.text.strip()
        
        # 説明文の取得
        desc_element = None
        desc_selectors = [
            ".excerpt",
            ".summary",
            ".description",
            ".post-excerpt",
            ".entry-summary",
            "p"
        ]
        
        for desc_sel in desc_selectors:
            desc_element = item.select_one(desc_sel)
            if desc_element and desc_element.text.strip():
                break
        
        desc = desc_element.text.strip() if desc_element else ""
        # 長い説明文は短縮
        if len(desc) > 200:
            desc = desc[:200] + "..."
        
        news_item = f"- [{parsed_date.strftime('%Y-%m-%d')}] {title}"
        if desc:
            news_item += f": {desc}"
        
        news.append(news_item)
        print(f"アイテム {i}: 追加しました - {title}")

    print(f"\n合計 {len(news)} 件の1週間以内の記事を取得しました")
    return "\n".join(news)

# === Step 3: Claudeに要約させる ===
def summarize_with_claude(news_text):
    if not news_text.strip():
        return "この1週間、AIエンジニアに関連する新しいAWSアップデートはありませんでした。"
    
    prompt = f"""
以下はAWS公式の1週間分の新着情報です。
あなたはAIに興味があるエンジニアです。
以下の情報から、あなたにとって関係が深いものだけを選び、要約してください：

{news_text}

---
出力形式：
1. 関連があるトピック名
2. なぜ関係があるのか一言説明
3. できれば内容の要約（1行）
4. 参考にした原本（抜粋or要約対象）

もし関連するトピックがない場合は、「この1週間、AIエンジニアに特に関連する大きなアップデートはありませんでした」と回答してください。
"""
    return agent(prompt)

# === 実行部分 ===
if __name__ == "__main__":
    print("🔎 AWS What's New RSSフィードを収集中...")
    news = scrape_aws_news_rss()
    
    # RSSフィードが失敗した場合のフォールバック
    if not news:
        print("🔄 RSSフィードが失敗したため、AWS News Blogを試行中...")
        news = scrape_aws_news()
    
    if news:
        print("🧠 Claudeが要約中...")
        summary = summarize_with_claude(news)
        print("\n===== 今週のピックアップまとめ =====\n")
        print(summary)
        print("\n==================================\n")
    else:
        print("❌ ニュースの取得に失敗しました。サイトの構造が変更されている可能性があります。")
