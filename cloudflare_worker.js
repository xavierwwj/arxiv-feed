/**
 * Telegram webhook handler.
 * Listens for "save 1 3 5" messages and triggers the GitHub Actions
 * save_papers workflow with those indices.
 *
 * Required environment variables (set as Worker secrets):
 *   TELEGRAM_BOT_TOKEN  - your bot token
 *   TELEGRAM_CHAT_ID    - allowed group or personal chat ID (security: ignore other chats)
 *   GITHUB_TOKEN        - personal access token with workflow write scope
 *   GITHUB_REPO         - e.g. "xavierwwj/arxiv-feed"
 *   GITHUB_BRANCH       - e.g. "master"
 */

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("OK", { status: 200 });
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return new Response("Bad request", { status: 400 });
    }

    const message = body?.message;
    if (!message?.text) return new Response("OK", { status: 200 });

    const chatId = String(message.chat.id);
    const text   = message.text.trim();

    console.log(`Incoming chatId: ${chatId}, allowed: ${env.TELEGRAM_CHAT_ID}`);

    // ignore messages from other chats
    if (chatId !== env.TELEGRAM_CHAT_ID) {
      console.log(`Rejected chat ${chatId}`);
      return new Response("OK", { status: 200 });
    }

    if (text.toLowerCase().startsWith("save ")) {
      const indices = text.slice(5).trim();

      if (!/^[\d\s]+$/.test(indices)) {
        await telegram(env, chatId, "⚠️ Use numbers only, e.g. save 1 3 5");
        return new Response("OK", { status: 200 });
      }

      const ghRes = await fetch(
        `https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/save_papers.yml/dispatches`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${env.GITHUB_TOKEN}`,
            Accept: "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "User-Agent": "arxiv-feed-bot",
          },
          body: JSON.stringify({
            ref: env.GITHUB_BRANCH,
            inputs: { indices },
          }),
        }
      );

      if (ghRes.status === 204) {
        await telegram(env, chatId, `⏳ Saving papers ${indices}… you'll get a confirmation shortly.`);
      } else {
        const err = await ghRes.text();
        await telegram(env, chatId, `❌ Failed to trigger save (${ghRes.status}): ${err}`);
      }
    }

    return new Response("OK", { status: 200 });
  },
};

async function telegram(env, chatId, text) {
  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text }),
  });
}
