# Trojaino on Windows: quick start

Trojaino checks new software before Claude Code installs it.
This takes about 10 minutes. You do not need to know how to code.

## Rules

- Do one step at a time, in order.
- Each step says **what you should see**. If you see something different, stop and take a picture of the screen.
- Never choose **Run as administrator**.
- Never click **Run anyway**, and never turn off antivirus.

You need Claude Code already working on this computer.

---

## Step 1. Open PowerShell

1. Click the **Start** button.
2. Type **PowerShell**.
3. Click **Windows PowerShell**.

**You should see:** a window with a line that ends in `>`. This is where you type.

To run a command from this guide: type it (or copy it and **right-click** in the window to paste), then press **Enter**.

## Step 2. Check for Python

Type this and press **Enter**:

```powershell
python3 --version
```

- If you see `Python 3.11`, `3.12`, `3.13` or `3.14` followed by more numbers, **skip to Step 4**.
- Anything else (an error, "not recognized", a Microsoft Store window, or an older version): go to Step 3.

## Step 3. Install Python

Type this and press **Enter**:

```powershell
winget install 9NQ7512CXL7T -e --accept-package-agreements
```

This installs the **Python Install Manager** from Microsoft's app store. It takes a minute or two.

**You should see:** `Successfully installed`.

Then:

1. **Close PowerShell** and open it again, like in Step 1.
2. Type this and press **Enter**. Answer **Y** to any question it asks.

```powershell
py install default
```

3. Close PowerShell, open it again, and go back to **Step 2**.

If Step 2 still does not show a version, stop.

## Step 4. Start Claude

Type this and press **Enter**:

```powershell
claude
```

## Step 5. Install Trojaino

In Claude, type this and press **Enter**:

```
/plugin marketplace add BlockhouseSoftware/claude-marketplace
```

**You should see:** a message that the marketplace was added.

Then type this and press **Enter**:

```
/plugin install trojaino@blockhouse-software
```

**You should see:** a message that Trojaino was installed.

## Step 6. Restart Claude

1. Type `/exit` and press **Enter**.
2. Type `claude` and press **Enter**.

## Step 7. Check that Trojaino is on

1. In Claude, type `/hooks` and press **Enter**.
2. Look for **SessionStart** and **PreToolUse**. Each one should mention **trojaino**.
3. Press **Escape**.

**That's it.** Trojaino is now on, and it stays on. You do not need to turn it on or off.

---

## What happens now

When Claude tries to install something, Trojaino checks it first:

| What Trojaino finds | What you see |
| --- | --- |
| No warning signs | Nothing. The install continues as normal. |
| Warning signs (**CAUTION**) | Claude asks you, and shows what Trojaino found. You decide. |
| Serious danger (**DO NOT RUN**) | The install is stopped. |
| Something it cannot check | Claude asks you, and says why. You decide. |

When Claude asks you, read what Trojaino says. If you are not sure, choose **No**.

Everything else Claude does works exactly as before.

## Updating Trojaino

In Claude, type:

```
/plugin update trojaino@blockhouse-software
```

## If something goes wrong

| What you see | What to do |
| --- | --- |
| `winget is not recognized` | Open the **Microsoft Store**, search for **Python Install Manager**, click **Get**, then continue from Step 3, number 1. |
| Windows asks for an administrator password | Click **Cancel**. Stop. |
| "Windows protected your PC" | Do not click Run anyway. Stop. |
| A **hook error** that mentions Python | Python is not set up. Go back to Step 2. |
| `/hooks` does not show trojaino | Type `/plugin`, check that trojaino is installed and enabled, then restart Claude. |

---

### Good to know

Trojaino is not antivirus. "No warning signs" means its rules found nothing in the files it read, not that a program is safe. It checks the package being installed, not the other packages that package pulls in. It checks what Claude installs, not what you install yourself.
