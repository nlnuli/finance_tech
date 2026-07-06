import { useCallback, useState } from "react";

import { ApiMessage, getThreadMessages } from "../api";

export function useMessages() {
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);

  const loadMessages = useCallback(async (threadId: string): Promise<ApiMessage[]> => {
    setIsLoadingMessages(true);
    try {
      return await getThreadMessages(threadId);
    } finally {
      setIsLoadingMessages(false);
    }
  }, []);

  return {
    isLoadingMessages,
    loadMessages,
  };
}
