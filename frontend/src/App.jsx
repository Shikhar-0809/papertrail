import { useState } from 'react';
import Dashboard from './components/Dashboard';
import ExamManager from './components/ExamManager';
import ForensicsLab from './components/ForensicsLab';
import AuditTrail from './components/AuditTrail';

const TABS = [
  { id: 'dashboard',   label: 'Dashboard' },
  { id: 'exams',       label: 'Exam Manager' },
  { id: 'forensics',   label: 'Forensics Lab' },
  { id: 'audit',       label: 'Audit Trail' },
];

function TabBar({ active, onSelect }) {
  return (
    <nav className="flex border-b border-gray-700 bg-gray-900">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onSelect(tab.id)}
          className={
            `px-6 py-3 text-sm font-medium tracking-wide transition-colors ` +
            (active === tab.id
              ? 'border-b-2 border-indigo-400 text-indigo-400'
              : 'text-gray-400 hover:text-gray-200')
          }
        >
          {tab.label}
        </button>
      ))}
    </nav>
  );
}

function Header() {
  return (
    <header className="bg-gray-950 border-b border-gray-800 px-8 py-4">
      <h1 className="text-xl font-bold text-white tracking-tight">
        ExamShield
      </h1>
      <p className="text-xs text-gray-500 mt-0.5">
        Cryptographic Exam Distribution &amp; Leak Tracing
      </p>
    </header>
  );
}

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');

  const page = {
    dashboard: <Dashboard />,
    exams:     <ExamManager />,
    forensics: <ForensicsLab />,
    audit:     <AuditTrail />,
  }[activeTab];

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 flex flex-col">
      <Header />
      <TabBar active={activeTab} onSelect={setActiveTab} />
      <main className="flex-1 overflow-auto">
        {page}
      </main>
    </div>
  );
}
