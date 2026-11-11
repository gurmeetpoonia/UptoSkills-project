const axios = require("axios");
const { GoogleGenAI } = require("@google/genai");

const AI_URL = process.env.AI_URL;
const TIMEOUT = process.env.AI_TIMEOUT || 5000;

const axiosInstance = axios.create({
  timeout: TIMEOUT,
});

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const isTransientAiError = (err) => {
  const msg = String(err?.message || "");
  return (
    /"code":\s*(429|500|503|504)|UNAVAILABLE|RESOURCE_EXHAUSTED|DEADLINE_EXCEEDED|timed out|ECONNRESET|ETIMEDOUT|fetch failed/i.test(msg) ||
    [429, 500, 503, 504].includes(Number(err?.status || err?.code))
  );
};

const withTimeout = (promise, ms) =>
  Promise.race([
    promise,
    new Promise((_, reject) =>
      setTimeout(() => reject(new Error(`Gemini request timed out after ${ms}ms`)), ms)
    ),
  ]);

// Retries transient Gemini errors (503/429/timeouts) and optionally falls back
// to a second model so a short Google overload doesn't block campaign emails.
const generateWithRetry = async (ai, request) => {
  const primary = process.env.GEMINI_MODEL || "gemini-2.5-flash";
  const fallback = process.env.GEMINI_FALLBACK_MODEL;
  const models = fallback && fallback !== primary ? [primary, primary, fallback] : [primary, primary];
  const timeoutMs = Number(process.env.GEMINI_REQUEST_TIMEOUT_MS || 20000);

  let lastError;
  for (let attempt = 0; attempt < models.length; attempt++) {
    try {
 console.log(
      `[Gemini] Attempt ${attempt + 1}/${models.length} using model: ${models[attempt]}`
    );
      return await withTimeout(
        ai.models.generateContent({ ...request, model: models[attempt] }),
        timeoutMs
      );
    } catch (err) {
      lastError = err;
      if (!isTransientAiError(err) || attempt === models.length - 1) break;
      await sleep(1000 * 2 ** attempt); // 1s, then 2s
    }
  }
  throw lastError;
};

/*
  Outreach message generation
 */
exports.generateOutreachMessage = async ({ name, company, purpose }) => {
  try {
    const payload = {
      type: "outreach",
      prompt: `Write a short professional outreach message.
Name: ${name}
Company: ${company}
Purpose: ${purpose}`,
    };

    const response = await axiosInstance.post(AI_URL, payload);

    return {
      output: response.data.output || response.data,
    };
  } catch (error) {
    console.error("AI Outreach error:", error.message);
    throw new Error("AI outreach service unavailable");
  }
};

/*
 AI-powered campaign personalization
 */
const AUDIENCE_PROMPTS = {
  status_new: "Write a professional B2B email for a new lead. Introduce the value clearly, establish relevance, and use a low-friction call to action without assuming prior contact.",
  status_contacted: "Write a concise follow-up for a contacted lead. Build naturally on the fact that outreach has already occurred, provide useful value, and suggest a clear next step without being repetitive or pushy.",
  status_in_progress: "Write a focused B2B email for a lead currently in progress. Move the existing sales conversation forward with relevant value and a specific next step.",
  status_converted: "Write a professional relationship-oriented email for a converted lead. Reinforce the value of the relationship and suggest an appropriate next step without treating the lead as a cold prospect.",
  status_closed: "Write a respectful B2B email for a closed lead. Keep the message concise and context-aware, and only suggest a next step if it is genuinely appropriate.",
  status_lost: "Write a thoughtful re-engagement email for a lost lead. Acknowledge that the previous opportunity did not progress without inventing reasons, offer relevant value, and use a low-pressure call to action.",
  all: "Write professional B2B outreach appropriate for a general lead audience.",
  default: "Write professional, concise B2B outreach appropriate for the selected campaign audience.",
};

const resolveAudiencePrompt = ({ audienceType = "all", audienceContext = {} } = {}) => {
  if (audienceType === "status") {
    const key = String(audienceContext.status || "").toLowerCase();
    const statusKey = `status_${key}`;
    return AUDIENCE_PROMPTS[statusKey] || AUDIENCE_PROMPTS.default;
  }

  if (audienceType === "all") return AUDIENCE_PROMPTS.all;

  if (audienceType === "tag") {
    return "Write B2B outreach specifically relevant to the selected tag audience. Use the tag context to shape the message, but do not claim facts about the lead that are not supplied.";
  }

  if (audienceType === "segment") {
    return "Write B2B outreach specifically relevant to the saved segment. Use the segment name and its actual filters/conditions to shape the message while using only supplied lead data as factual information.";
  }

  if (audienceType === "score") {
    return "Write B2B outreach appropriate to the selected lead-score range. Use the score audience context to calibrate relevance and sales intent, but do not mention or invent a score-based fact unless it is useful and supported.";
  }

  return AUDIENCE_PROMPTS.default;
};

exports.personalizeCampaignEmail = async ({
  name,
  company,
  jobTitle,
  industry,
  location,
  leadStatus,
  leadScore,
  campaignName,
  campaignDescription,
  audienceLabel,
  audienceType,
  audienceContext,
  stepNumber,
  selectedDraft,
}) => {
  try {
    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) throw new Error("GEMINI_API_KEY is not configured");

    const ai = new GoogleGenAI({ apiKey });
    const model = process.env.GEMINI_MODEL || "gemini-2.5-flash";
    const normalizedAudienceType = audienceType || "all";
    const normalizedAudienceContext =
      audienceContext && typeof audienceContext === "object"
        ? audienceContext
        : {};
    const audiencePrompt = resolveAudiencePrompt({
      audienceType: normalizedAudienceType,
      audienceContext: normalizedAudienceContext,
    });

    const audienceContextText = JSON.stringify(normalizedAudienceContext);

    const prompt = `You are generating one personalized B2B campaign email for one specific lead.

Campaign: ${campaignName || "Sales outreach"}
Campaign context: ${campaignDescription || "Professional B2B outreach"}
Step: ${stepNumber || 1}
Audience type: ${normalizedAudienceType}
Audience label: ${audienceLabel || "General Leads"}
Audience context and conditions: ${audienceContextText}
Audience-specific instruction:
${audiencePrompt}

Approved campaign draft selected by the campaign owner (use as the source/style; personalize it for this lead, preserving its intent and CTA):
Subject: ${selectedDraft?.subject || "No approved draft supplied; create suitable copy."}
Body: ${selectedDraft?.body || ""}

Authoritative lead data from the application database:
Name: ${name || ""}
Company: ${company || ""}
Job Title: ${jobTitle || ""}
Industry: ${industry || ""}
Location: ${location || ""}
Lead Status: ${leadStatus || ""}
Lead Score: ${leadScore ?? ""}

Rules:
- Generate a concise, natural, professional B2B email for THIS lead.
- Use the audience type and audience context/conditions to make the message relevant to this specific campaign audience.
- Use only the lead data and audience context supplied above as factual information.
- Never invent achievements, products, pain points, customers, numbers, relationships, reasons for status changes, or other facts.
- Make the wording meaningfully personalized to the available lead data.
- Include a clear but non-pushy call to action.
- Return ONLY valid JSON with exactly two string fields: "subject" and "body".
- Do not include markdown fences or explanations.
- The body should be ready to send as HTML-safe plain email text.`;

        const response = await generateWithRetry(ai, {
      contents: [{ role: "user", parts: [{ text: prompt }] }],
    });

    const raw = response.text?.trim();
    if (!raw) throw new Error("Gemini returned an empty response");

    const cleaned = raw.replace(/^\`\`\`(?:json)?\s*/i, "").replace(/\s*\`\`\`$/i, "").trim();
    let parsed;
    try {
      parsed = JSON.parse(cleaned);
    } catch {
      throw new Error("Gemini returned invalid email JSON");
    }

    if (!parsed?.subject?.trim() || !parsed?.body?.trim()) {
      throw new Error("Gemini returned incomplete email content");
    }

    return {
      subject: parsed.subject.trim(),
      body: parsed.body.trim(),
    };
  } catch (error) {
    console.error("AI Campaign Personalization error:", error.message);
    throw new Error("AI campaign personalization service unavailable");
  }
};
/*
 AI-powered campaign email generation
 */
exports.generateCampaignEmail = async ({
  name,
  company,
  jobTitle,
  industry,
  location,
  purpose,
  context,
  tone = "professional",
}) => {
  try {
    const apiKey = process.env.GEMINI_API_KEY;

    if (!apiKey) {
      throw new Error("GEMINI_API_KEY is not configured");
    }

    const ai = new GoogleGenAI({ apiKey });
    const model = process.env.GEMINI_MODEL || "gemini-2.5-flash";

    const prompt = `Generate a professional B2B sales email for the following lead.

Lead:
Name: ${name || ""}
Company: ${company || ""}
Job Title: ${jobTitle || ""}
Industry: ${industry || ""}
Location: ${location || ""}

Campaign purpose:
${purpose || ""}

Additional context:
${context || ""}

Tone:
${tone}

Rules:
- Use only the information provided.
- Do not invent facts about the lead or company.
- Keep the email concise and natural.
- Do not use generic exaggerated claims.
- Return ONLY valid JSON.
- Do not use markdown code fences.

Return exactly:
{
  "subject": "",
  "body": ""
}`;

    const response = await ai.models.generateContent({
      model,
      contents: [{ role: "user", parts: [{ text: prompt }] }],
    });

    const text = response.text?.trim();

    if (!text) {
      throw new Error("Gemini returned an empty response");
    }

    const cleaned = text
      .replace(/^```json\s*/i, "")
      .replace(/^```\s*/i, "")
      .replace(/\s*```$/i, "")
      .trim();

    const result = JSON.parse(cleaned);

    if (!result.subject || !result.body) {
      throw new Error("Gemini returned incomplete email data");
    }

    return {
      subject: result.subject,
      body: result.body,
    };
  } catch (error) {
    console.error(
      "AI Campaign Email Generation error:",
      error.message
    );

    throw new Error("AI campaign email generation service unavailable");
  }
};

/*
 Content summarization
 */
exports.summarizeContent = async (text) => {
  try {
    const payload = {
      type: "summarize",
      prompt: `Summarize the following text:\n${text}`,
    };

    const response = await axiosInstance.post(AI_URL, payload);

    return {
      output: response.data.output || response.data,
    };
  } catch (error) {
    console.error("AI Summary error:", error.message);
    throw new Error("AI summarization service unavailable");
  }
};
/*
 AI-powered reply intelligence
 */
exports.analyzeEmailReply = async ({
  replyBody,
  leadName,
  company,
  jobTitle,
}) => {
  try {
    const apiKey = process.env.GEMINI_API_KEY;

    if (!apiKey) {
      throw new Error("GEMINI_API_KEY is not configured");
    }

    const ai = new GoogleGenAI({ apiKey });
    const model = process.env.GEMINI_MODEL || "gemini-2.5-flash";

    const prompt = `Analyze this incoming B2B sales email reply.

Lead:
Name: ${leadName || ""}
Company: ${company || ""}
Job Title: ${jobTitle || ""}

Reply:
${replyBody}

Return ONLY valid JSON with exactly these fields:
{
  "intent": "INTERESTED|MEETING_REQUEST|QUESTION|NOT_INTERESTED|OUT_OF_OFFICE|OTHER",
  "sentiment": "POSITIVE|NEUTRAL|NEGATIVE",
  "summary": "short summary of what the lead said",
  "suggestedAction": "short recommended next action",
  "suggestedReply": "short professional reply"
}

Rules:
- Classify only from the supplied reply.
- Do not invent facts.
- If the lead asks for a meeting, use MEETING_REQUEST.
- If the lead shows buying interest without explicitly requesting a meeting, use INTERESTED.
- If the lead asks for information or clarification, use QUESTION.
- If the lead clearly declines, use NOT_INTERESTED.
- If it is an automatic absence message, use OUT_OF_OFFICE.
- Keep summary and suggestedAction concise.
- Keep suggestedReply professional and natural.`;

    const response = await ai.models.generateContent({
      model,
      contents: [{ role: "user", parts: [{ text: prompt }] }],
    });

    const text = response.text?.trim();

    if (!text) {
      throw new Error("Gemini returned an empty response");
    }

    const cleaned = text
      .replace(/^```json\s*/i, "")
      .replace(/^```\s*/i, "")
      .replace(/\s*```$/i, "")
      .trim();

    const result = JSON.parse(cleaned);

    return {
      intent: result.intent,
      sentiment: result.sentiment,
      summary: result.summary,
      suggestedAction: result.suggestedAction,
      suggestedReply: result.suggestedReply,
    };
  } catch (error) {
    console.error("AI Reply Intelligence error:", error.message);
    throw new Error("AI reply intelligence service unavailable");
  }
};

/**
 * Generate two campaign-level email alternatives for review. This endpoint never sends mail.
 */
exports.generateCampaignDraftOptions = async ({ campaignName, prompt, tone, goal, valueProposition, audienceLabel, lead }) => {
  if (!process.env.GEMINI_API_KEY) throw new Error("Gemini is not configured: GEMINI_API_KEY is missing");
  const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
  const safeLead = lead || {};
  const requestPrompt = `Create exactly two distinct B2B outreach email alternatives for a campaign.
Campaign: ${campaignName || "Untitled campaign"}
Audience: ${audienceLabel || "Selected leads"}
User prompt / keywords: ${prompt || "Write relevant, concise outreach"}
Tone: ${tone || "professional"}
Goal: ${goal || "replies"}
Value proposition: ${valueProposition || "Not specified"}
Representative lead context (use only facts supplied; do not invent): name=${safeLead.name || "unknown"}, company=${safeLead.companyName || safeLead.company || "unknown"}, job title=${safeLead.jobTitle || "unknown"}, industry=${safeLead.industry || "unknown"}, location=${safeLead.location || "unknown"}.
Return ONLY JSON: {"drafts":[{"subject":"...","body":"..."},{"subject":"...","body":"..."}]}.
Both drafts must have different angles, a clear but non-pushy CTA, and plain text bodies. Do not include markdown fences, placeholders, or unsupported claims.`;
  try {
    const response = await generateWithRetry(ai, { contents: [{ role: "user", parts: [{ text: requestPrompt }] }] });
    const raw = response.text?.trim();
    if (!raw) throw new Error("Gemini returned an empty response");
    const cleaned = raw.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/i, "").trim();
    const parsed = JSON.parse(cleaned);
    if (!Array.isArray(parsed?.drafts) || parsed.drafts.length < 2) throw new Error("Gemini did not return two drafts");
    const drafts = parsed.drafts.slice(0, 2).map((draft) => ({
      subject: String(draft?.subject || "").trim(),
      body: String(draft?.body || "").trim(),
    }));
    if (drafts.some((draft) => !draft.subject || !draft.body)) throw new Error("Gemini returned incomplete drafts");
    return drafts;
  } catch (error) {
    console.error("Campaign draft generation error:", error.message);
    throw new Error("Could not generate two email drafts. Check Gemini configuration and try again.");
  }
};
