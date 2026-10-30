// backend/controllers/notificationController.js me replace karein:

const deleteNotification = asyncHandler(async (req, res) => {
  const id = Number(req.params.id);
  const userId = Number(req.user.id);

  const result = await prisma.notification.deleteMany({
    where: {
      id,
      userId,
    },
  });

  if (result.count === 0) {
    return response.error(res, "Notification not found.", 404);
  }

  return response.success(res, { message: "Notification deleted." });
});

const deleteAllNotifications = asyncHandler(async (req, res) => {
  const userId = Number(req.user.id);

  const result = await prisma.notification.deleteMany({
    where: {
      userId,
    },
  });

  // Re-sync event emit karein taaki frontend/SSE sync ho jaye
  eventBus.publish(`user:${userId}`, {
    event: "notifications.read_all",
    payload: {},
    at: new Date().toISOString(),
  });

  return response.success(res, {
    message: "All notifications deleted.",
    deletedCount: result.count,
  });
});