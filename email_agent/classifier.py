import re
import json
from typing import Dict, Tuple

SYSTEM_PROMPT = """You are an executive email triage assistant. Score each email 0-100 for urgency and decide label.
Labels: urgent | attention | low
urgent = time-sensitive, financial/legal risk, outage, deadline <48h, CEO/boss direct request, security incident
attention = needs reply/decision this week, approvals, invoices, meeting requests, follow-ups
low = newsletters, FYI, marketing, spam, already handled

Return ONLY JSON: {"score": <0-100>, "label": "<urgent|attention|low>", "reason": "<short>", "suggested_action": "<e.g. reply, flag, escalate>"}
Be conservative: default to low unless strong signal.
"""

def heuristic_score(email: Dict, cfg: Dict) -> Tuple[int, str, str]:
    """Fast rule-based score before LLM."""
    subj = (email.get("subject") or "").lower()
    body = (email.get("bodyPreview") or email.get("body_preview") or "").lower()
    sender = (email.get("from", {}).get("emailAddress", {}).get("address") or "").lower()
    text = f"{subj} {body}"

    urgent_kw = [k.lower() for k in cfg["classifier"]["urgent_keywords"]]
    attn_kw = [k.lower() for k in cfg["classifier"]["attention_keywords"]]
    vip_senders = [s.lower() for s in cfg["classifier"].get("vip_senders", [])]
    vip_domains = [d.lower() for d in cfg["classifier"].get("vip_domains", [])]

    score = 10  # baseline
    reasons = []

    for kw in urgent_kw:
        if kw in text:
            score += 25
            reasons.append(f"keyword:{kw}")
            break
    for kw in attn_kw:
        if kw in text:
            score += 15
            reasons.append(f"keyword:{kw}")
            break

    if any(sender == v for v in vip_senders):
        score += 30
        reasons.append("vip_sender")
    if any(sender.endswith(f"@{d}") or sender.endswith(f".{d}") for d in vip_domains):
        score += 20
        reasons.append("vip_domain")

    # signals
    if email.get("importance") == "high":
        score += 15
        reasons.append("importance_high")
    if email.get("flag", {}).get("flagStatus") == "flagged":
        score += 10
    if email.get("hasAttachments"):
        # invoices / contracts often have attachments + keywords
        if any(k in text for k in ["invoice", "contract", "proposal", "statement"]):
            score += 10
            reasons.append("attachment+finance_kw")

    # recency boost handled by monitor (new mail = higher)
    # unread bonus
    if email.get("isRead") == False:
        score += 5

    score = max(0, min(100, score))
    th = cfg["classifier"]["thresholds"]
    if score >= th["urgent"]:
        label = "urgent"
    elif score >= th["attention"]:
        label = "attention"
    else:
        label = "low"

    return score, label, "; ".join(reasons) if reasons else "heuristic"

def llm_classify(email: Dict, cfg: Dict) -> Dict:
    """Call local LLM via OpenAI-compatible API. Returns {score,label,reason} or None on failure."""
    llm_cfg = cfg["classifier"]["llm"]
    if not llm_cfg.get("enabled"):
        return None
    # headless: if no API key configured, immediately fallback to heuristics (no hang)
    api_key = cfg["env"].get("llm_api_key") or ""
    if not api_key or api_key in ("ollama", "sk-...", "sk-placeholder-set-me", "env:OPENAI_API_KEY"):
        # empty or placeholder → skip LLM call
        if "sk-" not in api_key:
            return None
    try:
        from openai import OpenAI
        # resolve env: prefix
        base_url = llm_cfg["base_url"]
        if llm_cfg.get("api_key") == "env:OPENAI_API_KEY":
            api_key = cfg["env"].get("llm_api_key") or api_key
        client = OpenAI(base_url=base_url, api_key=api_key)
        subject = email.get("subject") or "(no subject)"
        sender = email.get("from", {}).get("emailAddress", {}).get("address", "unknown")
        preview = (email.get("bodyPreview") or "")[:800]
        importance = email.get("importance", "normal")
        has_attach = email.get("hasAttachments", False)
        is_read = email.get("isRead", True)
        received = email.get("receivedDateTime", "")

        user_msg = f"From: {sender}\nSubject: {subject}\nImportance: {importance} HasAttachment:{has_attach} IsRead:{is_read} Received:{received}\nPreview: {preview}"

        resp = client.chat.completions.create(
            model=llm_cfg["model"],
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            max_tokens=200,
        )
        content = resp.choices[0].message.content.strip()
        # extract JSON block
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if m:
            content = m.group(0)
        data = json.loads(content)
        # validate
        score = int(data.get("score", 0))
        label = data.get("label", "low").lower()
        if label not in ("urgent", "attention", "low"):
            label = "low"
        score = max(0, min(100, score))
        return {"score": score, "label": label, "reason": data.get("reason", ""), "suggested_action": data.get("suggested_action", "")}
    except Exception as e:
        # print for debug but don't crash
        # print(f"LLM classify failed: {e}")
        return None

def classify(email: Dict, cfg: Dict) -> Dict:
    h_score, h_label, h_reason = heuristic_score(email, cfg)
    llm_result = llm_classify(email, cfg) if cfg["classifier"]["llm"].get("enabled") else None
    if llm_result is None:
        # fallback to heuristic, optionally blend
        th = cfg["classifier"]["thresholds"]
        return {"score": h_score, "label": h_label, "reason": h_reason, "source": "heuristic", "suggested_action": "review" if h_label != "low" else "archive"}

    # blend: average but LLM dominates if heuristic is low
    # If LLM says urgent but heuristic low, trust LLM
    # If disagreement, take max for safety but require reasoning
    final_label = llm_result["label"]
    final_score = llm_result["score"]
    # safety: if heuristic strongly urgent (>80) and LLM says low, bump to attention
    if h_score >= 80 and llm_result["label"] == "low":
        final_label = "attention"
        final_score = max(final_score, 60)

    return {
        "score": final_score,
        "label": final_label,
        "reason": llm_result.get("reason") or h_reason,
        "source": "llm",
        "heuristic": {"score": h_score, "label": h_label, "reason": h_reason},
        "suggested_action": llm_result.get("suggested_action", ""),
    }
