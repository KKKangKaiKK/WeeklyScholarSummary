
# WeeklyScholarSummary

An intelligent, multi-client RSS summary bot designed for personalized weekly digests.

一个强大、可高度定制的 RSS 摘要机器人，专为您打造个性化的信息周报。

---


### 🚀 Introduction

**WeeklyScholarSummary** is a powerful and highly customizable RSS summary bot. It automatically scans your favorite RSS feeds, uses multiple Large Language Models (LLMs) to classify articles based on your interests, generates concise summaries for each topic, and outputs a beautifully formatted, email-friendly HTML report.

Its stateful, incremental scanning and robust caching mechanism ensure efficiency and reliability, making it the perfect tool to stay on top of your information streams without the noise.

### ✨ Key Features

-   **Multi-Client Parallel Processing**: Leverages multiple LLM endpoints (local or cloud-based) to classify a large number of articles in parallel, significantly speeding up the process.
-   **Stateful Incremental Scanning**: Remembers the articles processed last week and only fetches new ones, avoiding redundant work and API calls.
-   **Robust Caching Mechanism**: Saves progress at critical steps (after fetching, after classifying). If the script is interrupted, it can resume from where it left off.
-   **Custom LLM Server Support**: Works with any OpenAI-API compatible server and allows precise control over non-standard parameters (e.g., Qwen's `enable_thinking`).
-   **Per-Client Security Control**: Allows you to disable HTTPS certificate verification on a per-client basis, perfect for trusted local servers without a public certificate.
-   **Highly Compatible HTML Reports**: Generates a single, self-contained HTML file with inline CSS, ensuring maximum compatibility with email clients and platforms like the WeChat Official Accounts editor.
-   **Flexible Configuration**: All settings, including RSS feeds, topics of interest, and LLM client details, are managed in a simple `config.json` file.

### 🔧 How It Works

1.  **State Check**: The bot checks for a cache file from the previous week. If found, it prepares to scan for new articles from the last 8 days. If not, it performs an initial scan of the last 15 days.
2.  **Fetch New Articles**: It pulls articles from all configured RSS feeds, filtering out any that were processed in the previous run. The fetched articles are immediately cached.
3.  **Parallel Classification**: The classification workload is distributed among all configured LLM clients. Each article is sent to a client to determine which user-defined topic it belongs to. The classified results are then cached.
4.  **Summarization**: The primary LLM client (`llm_clients[0]`) is used to generate a coherent summary for all articles within each topic.
5.  **Report Generation**: The bot compiles the summaries and article links into a clean, professional HTML report with inline CSS.
6.  **Cleanup & State Update**: The bot cleans up intermediate cache files and saves the final classified articles as the state for the next week's run.

### ⚙️ Getting Started

#### 1. Prerequisites

-   Python 3.7+
-   Access to one or more OpenAI-API compatible LLM servers.

#### 2. Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/kkkangkaikk/WeeklyScholarSummary.git
    cd WeeklyScholarSummary/rss_bot
    ```

2.  Install the required dependencies:
    ```bash
    pip install feedparser requests beautifulsoup4
    ```

#### 3. Configuration

Copy or rename `config.example.json` to `config.json` and customize it to your needs.

```json
{
  "rss_feeds": [
    "https://rss.example.com/feed1",
    "http://rss.example2.com/feed"
  ],
  "interesting_topics": [
    "Artificial Intelligence",
    "Semiconductor Technology",
    "Space Exploration"
  ],
  "llm_clients": [
    {
      "name": "Primary Summarizer (Local)",
      "api_base": "https://localhost:11434/v1",
      "api_key": "YOUR_LOCAL_KEY",
      "model": "your-best-model-for-summary",
      "verify_ssl": false
    },
    {
      "name": "Classifier Worker (OpenRouter)",
      "api_base": "https://openrouter.ai/api/v1",
      "api_key": "YOUR_OPENROUTER_KEY",
      "model": "meta-llama/llama-3-8b-instruct",
      "verify_ssl": true,
      "extra_params": {
        "enable_thinking": false
      }
    }
  ],
  "output_filename": "weekly_summary.html",
  "cache_filename_prefix": "rss_bot_cache"
}
```

-   `rss_feeds`: A list of RSS feed URLs to scan.
-   `interesting_topics`: A list of topics you are interested in. The LLM will use these as classification categories.
-   `llm_clients`: A list of LLM client configurations.
    -   **The first client (`llm_clients[0]`) is special**: It is used for the final, high-quality summarization and won't participates in classification.
    -   **All other clients** are used as workers for parallel classification.
    -   `name`: A friendly name for logging.
    -   `api_base`: The base URL of the LLM API endpoint.
    -   `api_key`: The authentication key for the API.
    -   `model`: The name of the model to use.
    -   `verify_ssl`: Set to `false` only for trusted servers (like a local one) that use self-signed certificates.
    -   `extra_params` (Optional): A dictionary for sending non-standard parameters to the API, such as `{"enable_thinking": false}`.

#### 4. Running the Bot

Simply run the Python script from your terminal:

```bash
python rss_bot.py
```

The script will print its progress to the console. Once finished, you will find your report in the 'YYYY-MM-DD.html'.

### 📜 License

This project is distributed under the GNU GPLv3 License. See the `LICENSE` file for more information.

[** Click here to access **](https://kkkangkaikk.github.io/WeeklyScholarSummary/index.html)

---
---

## 中文版

### 🚀 项目简介

**WeeklyScholarSummary** 是一个强大且可高度定制的 RSS 摘要机器人。它能自动扫描您喜爱的 RSS 源，利用多个大语言模型（LLM）根据您的兴趣对文章进行并行分类，为每个主题生成精炼的摘要，并最终输出一个排版优美、对邮件客户端友好的 HTML 报告。

其独特的“有状态增量扫描”和“健壮的缓存机制”确保了运行的高效与稳定，使其成为您在信息洪流中保持领先、过滤噪音的完美工具。

### ✨ 核心功能

-   **多客户端并行处理**：利用多个 LLM 服务端点（本地或云端）并行处理大量文章的分类任务，极大提升处理速度。
-   **有状态的增量扫描**：能记住上周已处理过的文章，仅在新的一周拉取全新的内容，避免重复工作和不必要的 API 调用。
-   **健壮的缓存机制**：在关键步骤（如文章获取后、分类完成后）自动保存进度。如果程序意外中断，下次运行时可以从断点处继续，无需从头开始。
-   **支持自定义 LLM 服务**：兼容任何符合 OpenAI API 规范的服务端，并允许精确控制非标准参数（例如 Qwen 的 `enable_thinking`）。
-   **精准的独立安全控制**：允许您为每个客户端独立配置是否跳过 HTTPS 证书验证，完美适配没有公共证书的、可信的本地服务器。
-   **高度兼容的 HTML 报告**：生成包含内联 CSS 样式的单一、独立的 HTML 文件，确保在各类邮件客户端和微信公众号编辑器等平台中获得最佳显示效果。
-   **灵活的 JSON 配置**：所有设置（包括 RSS 订阅源、兴趣主题、LLM 客户端信息等）都通过一个简洁的 `config.json` 文件进行管理。

### 🔧 工作流程

1.  **状态检查**：机器人启动时会查找上周的缓存文件。若找到，则准备扫描过去 8 天的新文章；若未找到（首次运行），则执行 15 天的全量扫描。
2.  **拉取新文章**：从所有配置的 RSS 源中拉取文章，并自动过滤掉上一轮已处理过的内容。获取到的新文章列表会立即被缓存。
3.  **并行分类**：文章分类任务会被平均分配给配置文件中的所有 LLM 客户端。每篇文章被发送给一个客户端，以判断其所属的兴趣主题。分类完成的结果会被再次缓存。
4.  **生成总结**：使用主 LLM 客户端（配置列表中的第一个）为每个主题下的所有文章生成一段连贯的摘要。
5.  **生成报告**：将所有主题的摘要和相关文章链接编译成一个带有内联样式的、干净专业的 HTML 报告。
6.  **清理与状态更新**：机器人会清理本次运行产生的临时缓存文件，并将最终的分类结果保存为新的状态文件，供下一周运行时使用。

### ⚙️ 开始使用

#### 1. 环境要求

-   Python 3.7+
-   可以访问一个或多个兼容 OpenAI API 规范的 LLM 服务。

#### 2. 安装

1.  克隆本仓库：
    ```bash
    git clone https://github.com/kkkangkaikk/WeeklyScholarSummary.git
    cd WeeklyScholarSummary
    ```

2.  安装所需的依赖库：
    ```bash
    pip install feedparser requests beautifulsoup4
    ```

#### 3. 配置

将 `config.example.json` 文件复制或重命名为 `config.json`，然后根据您的需求进行修改。

```json
{
  "rss_feeds": [
    "https://www.ithome.com/rss/",
    "https://36kr.com/feed"
  ],
  "interesting_topics": [
    "人工智能",
    "芯片技术",
    "商业航天"
  ],
  "llm_clients": [
    {
      "name": "主总结模型 (本地)",
      "api_base": "https://localhost:11434/v1",
      "api_key": "YOUR_LOCAL_KEY",
      "model": "qwen:72b-chat",
      "verify_ssl": false
    },
    {
      "name": "分类工作模型 (OpenRouter)",
      "api_base": "https://openrouter.ai/api/v1",
      "api_key": "YOUR_OPENROUTER_KEY",
      "model": "meta-llama/llama-3-8b-instruct",
      "verify_ssl": true,
      "extra_params": {
        "enable_thinking": false
      }
    }
  ],
  "output_filename": "weekly_summary.html",
  "cache_filename_prefix": "rss_bot_cache"
}
```

-   `rss_feeds`: 您希望扫描的 RSS 订阅源 URL 列表。
-   `interesting_topics`: 您感兴趣的主题列表。LLM 将使用这些作为分类的类别。
-   `llm_clients`: LLM 客户端的配置列表。
    -   **第一个客户端 (`llm_clients[0]`) 非常特殊**：它专门用于生成最终的高质量摘要，不会参与分类工作。
    -   **所有其他客户端** 则作为工作节点，用于并行执行分类任务。
    -   `name`: 用于日志输出的友好名称。
    -   `api_base`: LLM API 的基础 URL。
    -   `api_key`: API 的身份验证密钥。
    -   `model`: 要使用的模型名称。
    -   `verify_ssl`: 是否验证 HTTPS 证书。仅对您信任的、使用自签名证书的本地服务器设置为 `false`。
    -   `extra_params` (可选): 一个字典，用于向 API 发送非标准参数，例如 `{"enable_thinking": false}`。

#### 4. 运行机器人

在您的终端中，直接运行 Python 脚本：

```bash
python rss_bot.py
```

脚本会在控制台打印出详细的执行进度。运行结束后，您将在项目目录下找到'YYYY-MM-DD.html'命名的报告文件。

### 📜 许可协议

本项目采用 GNU GPLv3 许可协议。详情请参阅 `LICENSE` 文件。

---

### 📊 查看报告示例 (View a Sample Report)

[**点击此处访问 **](https://kkkangkaikk.github.io/WeeklyScholarSummary/index.html)
