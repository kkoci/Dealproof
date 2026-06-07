import express from 'express';
import { createHash } from 'crypto';
import { Memory } from '@ekai/memory';

const PORT = Number(process.env.PORT ?? 4011);
const DB_PATH = process.env.MEMORY_DB_PATH ?? '/data/memory.db';

// Auto-detect provider from whichever API key is present in the environment.
// Priority: explicit MEMORY_PROVIDER env var > openai > gemini > openrouter.
function resolveProviderConfig(): { provider: 'openai' | 'gemini' | 'openrouter'; apiKey: string } {
  const explicit = (process.env.MEMORY_PROVIDER ?? '').toLowerCase();
  const candidates: Array<['openai' | 'gemini' | 'openrouter', string]> = [
    ['openai',     process.env.OPENAI_API_KEY     ?? ''],
    ['gemini',     process.env.GOOGLE_API_KEY      ?? ''],
    ['openrouter', process.env.OPENROUTER_API_KEY  ?? ''],
  ];

  if (explicit) {
    const match = candidates.find(([name]) => name === explicit);
    if (match && match[1]) return { provider: match[0], apiKey: match[1] };
    console.warn(`[memory] MEMORY_PROVIDER=${explicit} but its API key is not set — falling through`);
  }

  for (const [provider, apiKey] of candidates) {
    if (apiKey) {
      console.log(`[memory] using provider: ${provider}`);
      return { provider, apiKey };
    }
  }

  console.error('[memory] No API key found for any supported provider (OPENAI_API_KEY, GOOGLE_API_KEY, OPENROUTER_API_KEY). Memory add/search will fail.');
  return { provider: 'openai', apiKey: '' };
}

const { provider, apiKey } = resolveProviderConfig();

const mem = new Memory({
  provider,
  apiKey,
  dbPath: DB_PATH,
});

mem.addAgent('buyer', {
  name: 'Buyer Agent',
  soul: 'Data buyer agent inside a TEE. Remembers counterparty pricing patterns and past deal outcomes.',
  relevancePrompt: 'Only store memories about negotiation outcomes, pricing patterns, counterparty behaviour, and data quality signals.',
});
mem.addAgent('seller', {
  name: 'Seller Agent',
  soul: 'Data seller agent inside a TEE. Remembers buyer behaviour and optimal pricing anchors.',
  relevancePrompt: 'Only store memories about buyer willingness-to-pay, negotiation patterns, and deal terms accepted.',
});

const app = express();
app.use(express.json({ limit: '2mb' }));

app.get('/health', (_req, res) => {
  res.json({ status: 'ok' });
});

app.post('/memory/:agentId/add', async (req, res) => {
  const { agentId } = req.params;
  const { messages, userId } = req.body as {
    messages?: Array<{ role: string; content: string }>;
    userId?: string;
  };

  if (!messages || !messages.length) {
    return res.status(400).json({ error: 'messages is required' });
  }

  try {
    const result = await mem.agent(agentId).add(messages, { userId });
    res.json(result);
  } catch (err: any) {
    console.error('[add] error:', err?.message, err?.status, err?.code);
    res.status(500).json({ error: err?.message ?? 'add failed' });
  }
});

app.get('/memory/:agentId/search', async (req, res) => {
  const { agentId } = req.params;
  const q = req.query.q as string;

  if (!q || !q.trim()) {
    return res.status(400).json({ error: 'q query param is required' });
  }

  try {
    const results = await mem.agent(agentId).search(q);
    res.json({ results });
  } catch (err: any) {
    console.error('[search] error:', err?.message, err?.status, err?.code);
    res.status(500).json({ error: err?.message ?? 'search failed' });
  }
});

app.get('/memory/:agentId/hash', (req, res) => {
  const { agentId } = req.params;

  try {
    const records = mem.agent(agentId).memories({ limit: 100000 });
    const sorted = [...records].sort((a, b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
    const hash = sorted.length > 0
      ? createHash('sha256').update(JSON.stringify(sorted)).digest('hex')
      : '';
    res.json({ hash, count: sorted.length, timestamp: Date.now() });
  } catch (err: any) {
    res.status(500).json({ error: err?.message ?? 'hash failed' });
  }
});

app.listen(PORT, () => {
  console.log(`DealProof memory service listening on :${PORT}, db at ${DB_PATH}`);
});
