import React, { useEffect, useState, useRef } from "react";
import { notificationService } from "@/services";
import { openEventStream } from "@/lib/api";
import { Bell, BellRing, Trash2 } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { usePushNotifications } from "@/hooks/usePushNotifications";

const NotificationBell = () => {
  const { tokenStore } = useAuth();
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const dropdownRef = useRef(null);
  const { requestPermissionAndSubscribe, permission } = usePushNotifications();

  // Helper function to check read status across both DB conventions (read vs is_read)
  const isNotificationRead = (n) => Boolean(n.read || n.is_read);

  const load = async () => {
    try {
      const data = await notificationService.list({ limit: 20 });
      const list = data?.data || data || [];
      const safeList = Array.isArray(list) ? list : [];
      setItems(safeList);

      const unreadCount = data?.summary?.unreadCount !== undefined
        ? data.summary.unreadCount
        : safeList.filter((item) => !isNotificationRead(item)).length;

      setUnread(unreadCount);
    } catch (err) {
      console.error("[NotificationBell] Failed to load notifications:", err);
    }
  };

  useEffect(() => {
    let mounted = true;
    load();

    const stream = openEventStream("/sse/stream", {
      onEvent: (evt, data) => {
        if (!mounted) return;
        if (
          evt === "notification.new" ||
          evt === "notifications.read_all" ||
          [
            "LEAD_CREATED",
            "LEAD_UPDATED",
            "DEAL_CREATED",
            "DEAL_UPDATED",
            "PAYMENT_SUCCEEDED",
            "PAYMENT_FAILED",
            "USER_INVITED",
            "USER_JOINED",
            "INTEGRATION_SYNCED",
          ].includes(evt)
        ) {
          load();
        }

        if (evt === "notification.new" && data) {
          const payload = data.payload || data;
          const message = payload.message || "You have a new notification";
          const category = payload.category || "";
          const title = (category ? category.charAt(0).toUpperCase() + category.slice(1) : "New") + " Notification";

          if ("Notification" in window && Notification.permission === "granted") {
            try {
              new Notification(title, { body: message });
            } catch (e) {
              console.error("Failed to show OS notification:", e);
            }
          }
        }
      },
    });

    const id = setInterval(load, 60_000);
    return () => {
      mounted = false;
      stream.close();
      clearInterval(id);
    };
  }, []);

  // 1. [FIX]: Outer click par close hona
  useEffect(() => {
    const handleOutsideClick = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setOpen(false);
      }
    };

    if (open) {
      document.addEventListener("mousedown", handleOutsideClick);
    }
    return () => {
      document.removeEventListener("mousedown", handleOutsideClick);
    };
  }, [open]);

  // Mark all as read
  const markAll = async (e) => {
    e?.stopPropagation?.();
    try {
      await notificationService.markAllRead();
    } catch (err) {
      console.warn("markAllRead backend error:", err);
    } finally {
      setUnread(0);
      setItems((prev) => prev.map((n) => ({ ...n, read: true, is_read: true })));
    }
  };

  // Mark single as read
  const markOne = async (id, e) => {
    e?.stopPropagation?.();
    try {
      await notificationService.markRead(id);
    } catch (err) {
      console.warn("markRead backend error:", err);
    } finally {
      setUnread((u) => Math.max(0, u - 1));
      setItems((prev) =>
        prev.map((n) => (n.id === id ? { ...n, read: true, is_read: true } : n))
      );
    }
  };

  // 2. [FIX]: Clear All Notifications
  const deleteAll = async (e) => {
    e?.stopPropagation?.();
    try {
      if (typeof notificationService.removeAll === "function") {
        await notificationService.removeAll();
      } else if (typeof notificationService.deleteAll === "function") {
        await notificationService.deleteAll();
      }
    } catch (err) {
      console.warn("deleteAll backend error:", err);
    } finally {
      setItems([]);
      setUnread(0);
    }
  };

  // 3. [FIX]: Delete single notification
  const deleteOne = async (id, isRead, e) => {
    e?.stopPropagation?.();
    try {
      if (typeof notificationService.remove === "function") {
        await notificationService.remove(id);
      } else if (typeof notificationService.delete === "function") {
        await notificationService.delete(id);
      }
    } catch (err) {
      console.warn("deleteOne backend error:", err);
    } finally {
      setItems((prev) => prev.filter((n) => n.id !== id));
      if (!isRead) setUnread((u) => Math.max(0, u - 1));
    }
  };

  const handleEnablePush = (e) => {
    e?.stopPropagation?.();
    requestPermissionAndSubscribe?.();
  };

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setOpen((p) => !p)}
        className="relative inline-flex h-10 w-10 items-center justify-center rounded-xl border border-gray-200 bg-white text-gray-600 shadow-sm transition hover:bg-gray-100 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
        aria-label="Notifications"
      >
        <Bell className="h-5 w-5" />
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold text-white">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-80 max-w-[90vw] sm:w-96 overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-2xl dark:border-gray-800 dark:bg-gray-900">
          <div className="flex flex-col border-b border-gray-200 dark:border-gray-800">
            <div className="flex items-center justify-between px-4 py-3 text-sm font-semibold">
              <span>Notifications</span>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={markAll}
                  className="text-xs font-normal text-teal-600 hover:underline cursor-pointer"
                >
                  Mark all read
                </button>
                <button
                  type="button"
                  onClick={deleteAll}
                  className="text-xs font-normal text-red-500 hover:underline cursor-pointer"
                >
                  Clear all
                </button>
              </div>
            </div>

            {permission === "default" && (
              <div className="bg-teal-50 px-4 py-2 flex items-center justify-between dark:bg-teal-900/20">
                <span className="text-xs text-teal-800 dark:text-teal-200 flex items-center gap-1.5">
                  <BellRing size={14} /> Enable push notifications
                </span>
                <button
                  type="button"
                  onClick={handleEnablePush}
                  className="text-xs font-semibold text-teal-600 hover:underline dark:text-teal-400 cursor-pointer"
                >
                  Enable
                </button>
              </div>
            )}
          </div>

          <ul className="max-h-80 divide-y divide-gray-100 overflow-y-auto dark:divide-gray-800">
            {items.length === 0 ? (
              <li className="px-4 py-6 text-center text-sm text-gray-500">
                No notifications yet.
              </li>
            ) : (
              items.map((n) => {
                const isRead = isNotificationRead(n);
                return (
                  <li
                    key={n.id || Math.random()}
                    className={`group flex items-start gap-2 px-4 py-3 text-sm ${
                      isRead ? "" : "bg-teal-50/50 dark:bg-teal-900/10"
                    }`}
                  >
                    <div
                      className="mt-1 h-2 w-2 shrink-0 rounded-full"
                      style={{ background: isRead ? "transparent" : "#14b8a6" }}
                    />
                    <div className="flex-1">
                      <p className="font-medium text-gray-900 dark:text-white">
                        {n.message || n.title || "Notification"}
                      </p>
                      <p className="text-xs text-gray-500">
                        {n.type || "INFO"} · {n.createdAt ? new Date(n.createdAt).toLocaleString() : "Just now"}
                      </p>
                    </div>
                    <div className="flex flex-col items-end gap-2 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity">
                      {!isRead && (
                        <button
                          type="button"
                          onClick={(e) => markOne(n.id, e)}
                          className="text-xs text-teal-600 hover:underline cursor-pointer"
                        >
                          Read
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={(e) => deleteOne(n.id, isRead, e)}
                        className="text-gray-400 hover:text-red-500 transition-colors cursor-pointer"
                        title="Delete notification"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </li>
                );
              })
            )}
          </ul>
        </div>
      )}
    </div>
  );
};

export default NotificationBell;