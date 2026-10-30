import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage } from "./api";

/** 非同期取得の小さなフック */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorObj, setErrorObj] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const seq = useRef(0);

  const run = useCallback(() => {
    const my = ++seq.current;
    setLoading(true);
    setError(null);
    setErrorObj(null);
    fn()
      .then((d) => {
        if (my === seq.current) setData(d);
      })
      .catch((e) => {
        if (my === seq.current) {
          setError(errorMessage(e));
          setErrorObj(e);
        }
      })
      .finally(() => {
        if (my === seq.current) setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    run();
  }, [run]);

  return { data, setData, error, errorObj, loading, reload: run };
}

/** ボタン操作用：実行中フラグとエラーを持つ */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const exec = useCallback(async <R,>(fn: () => Promise<R>): Promise<R | undefined> => {
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(errorMessage(e));
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, error, setError, exec };
}
