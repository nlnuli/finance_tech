import { useCallback, useState } from "react";

import { getThreads, Thread } from "../api";

export function useThreads() {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [isLoadingThreads, setIsLoadingThreads] = useState(false);

  const loadThreads = useCallback(async () => {
    setIsLoadingThreads(true);
    try {
      const data = await getThreads();
      setThreads(data);
    } finally {
      setIsLoadingThreads(false);
    }
  }, []);

  return {
    threads,
    isLoadingThreads,
    loadThreads,
  };
}
