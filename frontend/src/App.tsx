import { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { api, track, type Meta } from "./api";
import { MetaContext } from "./common";
import Admin from "./pages/Admin";
import Answer from "./pages/Answer";
import Home from "./pages/Home";
import MapPage from "./pages/MapPage";
import NewTopic from "./pages/NewTopic";
import ResultsPage from "./pages/ResultsPage";

const VISIT_KEY = "seika.visited";

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null);

  useEffect(() => {
    api.meta().then(setMeta).catch(() => undefined);
    // 再訪率を測るため、ブラウザのセッションごとに1回だけ「訪問」を記録する
    let first = true;
    try {
      first = !sessionStorage.getItem(VISIT_KEY);
      sessionStorage.setItem(VISIT_KEY, "1");
    } catch {
      /* 保存できなくても記録は続ける */
    }
    if (first) track("visit");
  }, []);

  return (
    <MetaContext.Provider value={meta}>
      <header className="site-header">
        <div className="wrap header-inner">
          <NavLink to="/" className="brand">
            成果型SNS
          </NavLink>
          <nav className="nav">
            <NavLink to="/" end>
              議題
            </NavLink>
            <NavLink to="/map">価値観マップ</NavLink>
            <NavLink to="/new">議題を作る</NavLink>
          </nav>
        </div>
      </header>
      <main className="wrap main">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/t/:id" element={<Answer />} />
          <Route path="/t/:id/results" element={<ResultsPage />} />
          <Route path="/map" element={<MapPage />} />
          <Route path="/new" element={<NewTopic />} />
          <Route path="/admin" element={<Admin />} />
          <Route path="*" element={<div className="card">ページが見つかりません。</div>} />
        </Routes>
      </main>
      <footer className="wrap footer">
        <p>
          サービス改善のため、このサイトでの操作（開いた画面・回答・共有など）を記録しています。
          記録は端末ごとの番号にひも付き、名前やメールアドレスは集めていません。
        </p>
      </footer>
    </MetaContext.Provider>
  );
}
