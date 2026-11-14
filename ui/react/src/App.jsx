import { Routes, Route } from "react-router";
import Header from "./components/Header.jsx";
import Home from "./pages/Home.jsx";
import DatabaseMonitor from "./pages/DatabaseMonitor.jsx";

export default function App() {
  return (
    <div className="min-h-screen bg-kpmg-cobalt">
      <Header />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/database" element={<DatabaseMonitor />} />
      </Routes>
    </div>
  );
}
