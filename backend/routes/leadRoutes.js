const express = require("express");
const router = express.Router();
const ctrl = require("../controllers/leadController");
const findCtrl = require("../controllers/findLeadsController");
const ingestCtrl = require("../controllers/ingestController");
const multer = require("multer");
const { AppError } = require("../middleware/errorHandler");
const { protect } = require("../middleware/authMiddleware");
const tenantScope = require("../middleware/tenant");
const validate = require("../middleware/validate");
const {
  createLeadSchema,
  leadQuerySchema,
  updateLeadSchema,
} = require("../validations/leadValidation");
const { enforcePlanLimit } = require("../services/usageService");
const { permit } = require("../middleware/rbac");

router.use(protect, tenantScope);

router.get("/stats", ctrl.stats);
router.get("/", validate(leadQuerySchema, "query"), ctrl.getLeads);

// Find Leads Routes
router.post("/find", permit("OWNER", "ADMIN", "MEMBER"), findCtrl.findLeads);
router.get("/find/candidates", permit("OWNER", "ADMIN", "MEMBER"), findCtrl.getCandidates);
router.get("/find/:jobId", permit("OWNER", "ADMIN", "MEMBER"), findCtrl.getFindLeadsStatus);
router.post("/find/:jobId/confirm", permit("OWNER", "ADMIN", "MEMBER"), findCtrl.confirmFindLeads);

// Upload Excel / Run Scraper: file goes to the scraper through the backend (internal URL never reaches the browser).
const uploadFile = multer({ storage: multer.memoryStorage(), limits: { fileSize: 5 * 1024 * 1024, files: 1 } }).single("file");
const acceptUpload = (req, res, next) =>
  uploadFile(req, res, (err) => {
    if (!err) return next();
    if (err.code === "LIMIT_FILE_SIZE") return next(new AppError("The file is larger than 5 MB.", 413));
    return next(new AppError("Could not read the uploaded file.", 400));
  });
router.post("/ingest", permit("OWNER", "ADMIN", "MEMBER"), acceptUpload, ingestCtrl.startIngest);
router.get("/ingest/:jobId", permit("OWNER", "ADMIN", "MEMBER"), ingestCtrl.getIngestStatus);
router.post("/ingest/:jobId/save", permit("OWNER", "ADMIN", "MEMBER"), ingestCtrl.saveIngest);

router.get("/:id", ctrl.getLeadById);
router.post("/:id/enrich", permit("OWNER", "ADMIN", "MEMBER"), ctrl.enrichLead);
router.post(
  "/",
  permit("OWNER", "ADMIN", "MEMBER"),
  enforcePlanLimit("leads", "leads"),
  validate(createLeadSchema),
  ctrl.createLead,
);
router.patch("/:id", permit("OWNER", "ADMIN", "MEMBER"), validate(updateLeadSchema), ctrl.updateLead);
router.delete("/:id", permit("OWNER", "ADMIN", "MEMBER"), ctrl.deleteLead);
router.post("/bulk", permit("OWNER", "ADMIN", "MEMBER"), ctrl.bulkUpdate);
router.post("/bulk-delete", permit("OWNER", "ADMIN"), ctrl.bulkDelete);

module.exports = router;
