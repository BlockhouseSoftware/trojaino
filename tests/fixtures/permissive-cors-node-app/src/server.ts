import express from 'express';
import cors from 'cors';

const app = express();

// Alpha fixture: intentionally broad CORS for deterministic scanner coverage.
app.use(cors({ origin: '*', credentials: true }));

app.get('/api/profile', (_req, res) => {
  res.json({ ok: true });
});

app.listen(3000);
