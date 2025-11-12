import requests
import json
import os
import re
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import feedparser
from bs4 import BeautifulSoup
import html
import datetime



# --- 新增：抑制针对特定连接的 InsecureRequestWarning ---
# 我们将在代码中精确控制 SSL 验证，因此可以安全地禁用此警告
import urllib3
from urllib3.exceptions import InsecureRequestWarning
urllib3.disable_warnings(InsecureRequestWarning)
# ----------------------------------------------------

# --- 1. 配置与缓存管理 ---

def load_config(filename="config.json"):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"错误：配置文件 '{filename}' 未找到。请根据模板创建。")
        exit()

def save_cache(data, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"进度已保存到: {filename}")

def load_cache(filename):
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            print(f"从缓存加载: {filename}")
            return json.load(f)
    return None

# --- 2. 基于 Requests 的 LLM 客户端 ---

def requests_based_llm_call(client_config, prompt):
    """
    使用 requests 库调用 API，并根据配置决定是否验证 SSL 证书。
    """
    api_base = client_config['api_base']
    api_key = client_config['api_key']
    model = client_config['model']
    # 修改：从配置中读取 verify_ssl 值，如果未提供则默认为 True (安全)
    verify_ssl = client_config.get('verify_ssl', True)
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
    }

    try:
        response = requests.post(
            f"{api_base}/chat/completions",
            headers=headers,
            json=payload,
            verify=verify_ssl, # 核心修改：使用配置中的值
            timeout=120
        )
        response.raise_for_status()
        
        data = response.json()
        content = data['choices'][0]['message']['content']
        cleaned_content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
        return cleaned_content.strip()

    except requests.exceptions.RequestException as e:
        print(f"与 LLM 服务器 ({client_config['name']}) 通信时发生网络错误: {e}")
        return None
    except (KeyError, IndexError) as e:
        print(f"解析 LLM 服务器 ({client_config['name']}) 的响应时出错: {e}, 响应内容: {response.text}")
        return None

# --- 3. RSS 拉取与内容处理 ---

def get_article_full_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'}
        # 修改：移除 verify=False，恢复对外部网站的证书验证
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        article_body = soup.find('article') or soup.find('div', class_='post-content') or soup.find('div', class_='content')
        if article_body:
            return article_body.get_text(separator='\n', strip=True)
        return None
    except Exception:
        return None

def fetch_and_filter_rss(feed_urls, days_to_scan, existing_links):
    scan_since_date = datetime.now() - timedelta(days=days_to_scan)
    new_articles = []

    for url in feed_urls:
        print(f"正在处理 RSS源: {url}")
        feed = feedparser.parse(url)
        for entry in feed.entries:
            published_time = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                published_time = datetime.fromtimestamp(time.mktime(entry.published_parsed))
            
            if published_time and published_time >= scan_since_date:
                if entry.link in existing_links:
                    continue

                content = entry.get('summary', '')
                full_content = get_article_full_content(entry.link)
                if full_content:
                    content = full_content

                new_articles.append({
                    "title": entry.title,
                    "link": entry.link,
                    "content": content,
                    "published": published_time.strftime("%Y-%m-%d"),
                    "category": None
                })
    return new_articles

# --- 4. LLM 核心逻辑 (分类与总结) ---

def classify_article_worker(article_with_index, client_config, topics):
    index, article = article_with_index
    print(f"  [线程: {client_config['name']}] 正在分类: {article['title'][:30]}...")
    
    prompt = f"""
    请判断以下文章内容主要与哪个话题最相关。话题列表：{topics}。
    如果内容与任何一个话题都不太相关，请返回 "其他"。
    如果你支持推理/chain of thought，请缩短思考长度，如果不支持，请无视。
    请只返回最相关的话题名称，不要添加任何多余的解释。

    文章内容：
    ---
    {article['title']}
    {article['content'][:500]}
    ---
    最相关的话题是：
    """
    category = requests_based_llm_call(client_config, prompt)
    return index, category


def summarize_articles(client_config, articles_content):
    prompt = f"""
    请根据以下文章内容，为这个主题生成一个丰富、有条理的周报总结。
    请直接开始写总结，不要有引言。

    文章内容：
    ---
    {articles_content}
    ---
    本周总结：
    """
    return requests_based_llm_call(client_config, prompt)


# --- 5. HTML 生成 (内联 CSS) ---

def generate_html_inline_css(categorized_articles, summaries, filename):
    report_date = datetime.now().strftime('%Y-%m-%d')
    styles = {
        'body': 'font-family: "PingFang SC", "Microsoft YaHei", "Helvetica Neue", "Hiragino Sans GB", "Segoe UI", "Roboto", "Arial", sans-serif; line-height: 1.8; color: #333333; background-color: #f9f9f9; margin: 0; padding: 12px;',
        'container': 'max-width: 680px; margin: 0 auto; background-color: #ffffff; padding: 25px 30px; border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.08);',
        'header': 'text-align: center; border-bottom: 2px solid #eeeeee; padding-bottom: 20px; margin-bottom: 30px;',
        'h1': 'margin: 0; color: #2c3e50; font-size: 26px; font-weight: 600;',
        'date': 'color: #95a5a6; font-size: 14px; margin-top: 5px;',
        'category_section': 'margin-bottom: 35px;',
        'h2': 'color: #2980b9; border-bottom: 2px solid #3498db; padding-bottom: 8px; margin-top: 0; font-size: 22px; font-weight: 500;',
        'summary_box': 'background-color: #f8f9fa; padding: 18px 22px; border-radius: 5px; margin-bottom: 25px; border-left: 5px solid #3498db;',
        'h3': 'margin-top: 0; margin-bottom: 10px; color: #34495e; font-size: 18px; font-weight: 500;',
        'p': 'margin: 0;',
        'h4': 'margin-top: 0; margin-bottom: 15px; font-size: 16px; color: #34495e; font-weight: 500;',
        'ul': 'list-style-type: none; padding: 0; margin: 0;',
        'li': 'margin-bottom: 14px;',
        'a': 'text-decoration: none; color: #2c3e50; font-weight: 500; font-size: 16px;',
        'meta': 'color: #7f8c8d; font-size: 13px; margin-left: 8px;',
        'footer': 'text-align: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid #eeeeee; color: #bdc3c7; font-size: 12px;'
    }
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>每周RSS动态总结 - {report_date}</title>
    </head>
    <body style="{styles['body']}">
        <div style="{styles['container']}">
            <div style="{styles['header']}">
                <h1 style="{styles['h1']}">每周 RSS 动态总结</h1>
                <p style="{styles['date']}" class="date">{report_date}</p>
            </div>
    """

    if not summaries:
        html_content += "<p>本周没有发现与您感兴趣话题相关的新文章。</p>"
    else:
        for category, summary in summaries.items():
            safe_category = html.escape(category)
            formatted_summary = html.escape(summary).replace('\n', '<br>')
            
            html_content += f"""
            <div style="{styles['category_section']}">
                <h2 style="{styles['h2']}">{safe_category}</h2>
                <div style="{styles['summary_box']}">
                    <h3 style="{styles['h3']}">本周总结</h3>
                    <p style="{styles['p']}">{formatted_summary}</p>
                </div>
                <div>
                    <h4 style="{styles['h4']}">相关文章</h4>
                    <ul style="{styles['ul']}">
            """
            
            for article in categorized_articles[category]:
                safe_title = html.escape(article['title'])
                safe_link = html.escape(article['link'])
                safe_published = html.escape(article['published'])
                html_content += f"""
                        <li style="{styles['li']}">
                            <a href="{safe_link}" target="_blank" rel="noopener noreferrer" style="{styles['a']}">{safe_title}</a>
                            <span style="{styles['meta']}">- {safe_published}</span>
                        </li>
                """
            html_content += "</ul></div></div>"

    html_content += f"""
            <div style="{styles['footer']}">
                <p>由 RSS Summary Bot 自动生成</p>
            </div>
        </div>
    </body>
    </html>
    """

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"HTML 报告已生成: {filename}")

# --- 6. 主逻辑 ---

def main():
    config = load_config()
    prefix = config['cache_filename_prefix']
    
    last_week_file = f"{prefix}_last_week.json"
    fetched_file = f"{prefix}_fetched.json"
    classified_file = f"{prefix}_classified.json"

    last_week_data = load_cache(last_week_file)
    if last_week_data:
        days_to_scan = 8
        existing_links = {article['link'] for article in last_week_data}
        print(f"检测到上周记录，将扫描过去 {days_to_scan} 天的内容，并排除 {len(existing_links)} 个旧链接。")
    else:
        days_to_scan = 15
        existing_links = set()
        print(f"未检测到上周记录，将进行首次扫描，范围为过去 {days_to_scan} 天。")

    articles_to_process = load_cache(fetched_file)
    if not articles_to_process:
        print("\n--- 开始获取新文章 ---")
        articles_to_process = fetch_and_filter_rss(config['rss_feeds'], days_to_scan, existing_links)
        print(f"获取到 {len(articles_to_process)} 篇新文章。")
        save_cache(articles_to_process, fetched_file)
    else:
        print(f"从缓存加载了 {len(articles_to_process)} 篇待处理文章。")


    classified_articles = load_cache(classified_file)
    if not classified_articles:
        print("\n--- 开始并行分类文章 ---")
        clients = config['llm_clients'][1:]
        num_clients = len(clients)
        tasks = [( (i, article), clients[i % num_clients], config['interesting_topics'] ) for i, article in enumerate(articles_to_process)]
        
        with ThreadPoolExecutor(max_workers=num_clients) as executor:
            results = executor.map(lambda p: classify_article_worker(*p), tasks)

        for index, category in results:
            if category and category != "其他":
                articles_to_process[index]['category'] = category
        
        classified_articles = [a for a in articles_to_process if a['category']]
        print(f"分类完成，共有 {len(classified_articles)} 篇相关文章。")
        save_cache(classified_articles, classified_file)
    else:
         print(f"从缓存加载了 {len(classified_articles)} 篇已分类文章。")

    print("\n--- 开始生成总结 ---")
    categorized_articles = {}
    for topic in config['interesting_topics']:
        categorized_articles[topic] = [a for a in classified_articles if a['category'] == topic]

    summaries = {}
    summarizer_client = config['llm_clients'][0]
    for category, articles in categorized_articles.items():
        if not articles:
            continue
        print(f"正在总结类别: {category} ({len(articles)}篇文章)")
        combined_content = "\n\n---\n\n".join(
            [f"标题: {a['title']}\n内容摘要: {a['content'][:1000]}" for a in articles]
        )
        summary = summarize_articles(summarizer_client, combined_content)
        if summary:
            summaries[category] = summary

    print("\n--- 开始生成 HTML 报告 ---")

    today = datetime.date.today()
    formatted_date = today.strftime("%Y-%m-%d")
    generate_html_inline_css(categorized_articles, summaries, f"{formatted_date}.html")

    print("\n--- 清理缓存并更新状态 ---")
    if os.path.exists(last_week_file):
        os.remove(last_week_file)
        print(f"已删除旧的状态文件: {last_week_file}")
    
    if os.path.exists(classified_file):
        os.rename(classified_file, last_week_file)
        print(f"当前分类结果已存为下一周的记录: {last_week_file}")

    if os.path.exists(fetched_file):
        os.remove(fetched_file)
        print(f"已删除本次的中间缓存: {fetched_file}")

    print("\n任务全部完成！")


if __name__ == "__main__":
    main()
