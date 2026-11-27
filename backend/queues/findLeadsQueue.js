const { Queue, Worker } = require("bullmq");
const { bullmqConnection, redisClient } = require("../config/redis");
const axios = require("axios");
const { saveCandidates } = require("../services/findLeadCandidateService");

const queueName = "find-leads-queue";
const SCRAPER_API_URL = (
  process.env.JOB_SCRAPER_URL ||
  process.env.SCRAPER_URL ||
  process.env.SCRAPER_API_URL ||
  "http://localhost:8000"
).replace(/\/+$/, "");
const MAX_WAIT_MS = 3 * 60 * 1000; // stop waiting after 3 minutes (the scraper itself stops at ~40s)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const findLeadsQueue = new Queue(queueName, { connection: bullmqConnection });

const worker = new Worker(
  queueName,
  async (job) => {
    const { fastapiJobId, orgId, searchType } = job.data;
    const startedAt = Date.now();

    while (true) {
      if (Date.now() - startedAt > MAX_WAIT_MS) {
        throw new Error("Scraping took too long. Try a smaller search.");
      }

      let data;
      try {
        const response = await axios.get(
          `${SCRAPER_API_URL}/scrape/${fastapiJobId}`,
          { timeout: 30000 }
        );
        data = response.data;
      } catch (err) {
        if (err.response && err.response.status === 404) {
          throw new Error("The scraper lost this job (it may have restarted). Please search again.");
        }
        await sleep(5000);
        continue;
      }

      if (data.status === "done") {
        const leads = data.results || data.leads || [];
        await redisClient.set(
          `find-leads-result:${job.id}`,
          JSON.stringify(leads),
          { EX: 3600 }
        );
        await redisClient.set(
          `find-leads-note:${job.id}`,
          data.note || "",
          { EX: 3600 }
        );
        try {
          // Keep every found lead in the database (discovered ones get a "New" badge).
          await saveCandidates(orgId, leads, { markNew: searchType === "discover" });
        } catch (saveErr) {
          console.error("Could not save Find Leads candidates:", saveErr.message);
        }
        return { status: "done", count: leads.length };
      }
      if (data.status === "error") {
        throw new Error(data.error || "Scraper failed");
      }
      await sleep(5000);
    }
  },
  { connection: bullmqConnection }
);

worker.on("failed", (job, err) => {
  console.error(`FindLeads Job ${job.id} failed with error:`, err);
});

module.exports = {
  findLeadsQueue,
};