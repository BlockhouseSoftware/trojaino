import { exec } from "child_process";

router.delete('/api/delete-user', async (req, res) => {
  await db.user.delete({ where: { id: req.query.id } });
  res.json({ ok: true });
});

export function runCommand(cmd: string) {
  return exec(cmd);
}
