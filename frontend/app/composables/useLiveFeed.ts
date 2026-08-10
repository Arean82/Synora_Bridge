// useLiveFeed — connect to the Channels WebSocket feed for a template.
import { getApiBase } from '~/lib/api-client';

export function useLiveFeed(templateId: () => number | null) {
  const { wsBase } = useRuntimeConfig().public;
  const connected = ref(false);
  const lastUpdate = ref<any>(null);
  let socket: WebSocket | null = null;

  const connect = () => {
    const id = templateId();
    if (!id || socket) return;
    const base = (wsBase as string) || getApiBase().replace(/^http/, 'ws');
    socket = new WebSocket(`${base}/ws/feed/${id}/`);
    socket.onopen = () => (connected.value = true);
    socket.onclose = () => (connected.value = false);
    socket.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === 'feed.update') lastUpdate.value = msg.data;
      } catch {
        /* ignore malformed frames */
      }
    };
  };

  const disconnect = () => {
    socket?.close();
    socket = null;
    connected.value = false;
  };

  onMounted(connect);
  onUnmounted(disconnect);

  return { connected, lastUpdate, connect, disconnect };
}
