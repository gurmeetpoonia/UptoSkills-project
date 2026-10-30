import React, { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity, BarChart3, CalendarDays, CheckCircle2, ChevronDown, CircleHelp,
  Command, Filter, LayoutDashboard, Mail, Menu, Plus, Search, Settings,
  Sparkles, Target, Users, BriefcaseBusiness, ChartNoAxesCombined, FileText,
  Bell, ArrowUpRight, Clock3, X, ShieldCheck,
} from "lucide-react";

const NAV = [
  { label: "Overview", icon: LayoutDashboard, section: "Workspace" },
  { label: "Campaigns", icon: Mail, section: "Workspace" },
  { label: "Leads", icon: Users, section: "Workspace" },
  { label: "Deals", icon: BriefcaseBusiness, section: "Workspace" },
  { label: "Contacts", icon: Target, section: "Workspace" },
  { label: "Activities", icon: Activity, section: "Workspace" },
  { label: "Calendar", icon: CalendarDays, section: "Workspace" },
  { label: "Analytics", icon: ChartNoAxesCombined, section: "Insights" },
  { label: "Reports", icon: FileText, section: "Insights" },
];

const LEADS = [
  { name: "Olivia Rhye", company: "Orbit Labs", email: "olivia@example.test", status: "Qualified", score: 92, source: "Website" },
  { name: "Phoenix Baker", company: "Northstar", email: "phoenix@example.test", status: "New", score: 78, source: "Referral" },
  { name: "Lana Steiner", company: "Layers", email: "lana@example.test", status: "Contacted", score: 65, source: "Campaign" },
  { name: "Demi Wilkinson", company: "Catalog", email: "demi@example.test", status: "Qualified", score: 88, source: "Website" },
  { name: "Candice Wu", company: "Sisyphus", email: "candice@example.test", status: "New", score: 54, source: "LinkedIn" },
];
const CAMPAIGNS = [
  { name: "Q4 Product Launch", channel: "Email sequence", status: "Active", audience: "Enterprise prospects", sent: "2,480", rate: "42.8%" },
  { name: "October Newsletter", channel: "Newsletter", status: "Scheduled", audience: "All subscribers", sent: "—", rate: "—" },
  { name: "Re-engagement Series", channel: "Automated follow-up", status: "Draft", audience: "Inactive leads", sent: "—", rate: "—" },
];
const DEALS = [
  { name: "Enterprise Platform", company: "Orbit Labs", value: "$48,000", stage: "Negotiation", probability: "75%" },
  { name: "Growth Package", company: "Northstar", value: "$18,500", stage: "Proposal", probability: "55%" },
  { name: "Team Plan", company: "Layers", value: "$9,600", stage: "Qualified", probability: "35%" },
  { name: "Annual Renewal", company: "Catalog", value: "$24,000", stage: "Won", probability: "100%" },
];
const ACTIVITIES = [
  { title: "Follow-up call with Orbit Labs", detail: "Today · 11:30 AM", status: "Upcoming" },
  { title: "Q4 Product Launch email", detail: "Today · 1:00 PM", status: "Scheduled" },
  { title: "Proposal review — Northstar", detail: "Tomorrow · 10:00 AM", status: "Upcoming" },
  { title: "Weekly pipeline review", detail: "Oct 20 · 2:00 PM", status: "Planned" },
];
const fmt = (value) => value;

function Pill({ children, tone = "gray" }) {
  const tones = {
    green: "bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-300",
    blue: "bg-blue-50 text-blue-700 ring-blue-600/20 dark:bg-blue-500/10 dark:text-blue-300",
    amber: "bg-amber-50 text-amber-700 ring-amber-600/20 dark:bg-amber-500/10 dark:text-amber-300",
    gray: "bg-slate-100 text-slate-600 ring-slate-500/20 dark:bg-slate-800 dark:text-slate-300",
    violet: "bg-violet-50 text-violet-700 ring-violet-600/20 dark:bg-violet-500/10 dark:text-violet-300",
  };
  return <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${tones[tone] || tones.gray}`}>{children}</span>;
}

function SectionTitle({ eyebrow, title, description, action }) {
  return <div className="mb-6 flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs font-bold uppercase tracking-[0.16em] text-teal-600 dark:text-teal-400">{eyebrow}</p><h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-950 dark:text-white sm:text-3xl">{title}</h1>{description && <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{description}</p>}</div>{action}</div>;
}

function StatCard({ label, value, change, icon: Icon, color = "teal" }) {
  const colors = { teal: "bg-teal-50 text-teal-700 dark:bg-teal-500/10 dark:text-teal-300", violet: "bg-violet-50 text-violet-700 dark:bg-violet-500/10 dark:text-violet-300", blue: "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300", amber: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300" };
  return <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900"><div className="flex items-center justify-between gap-2"><span className="text-sm font-medium text-slate-500 dark:text-slate-400">{label}</span><span className={`rounded-xl p-2.5 ${colors[color]}`}><Icon className="h-5 w-5" /></span></div><div className="mt-4 flex items-end justify-between gap-2"><p className="text-3xl font-bold tracking-tight text-slate-950 dark:text-white">{value}</p><span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">{change}</span></div></article>;
}

function Table({ headers, rows }) {
  return <div className="overflow-x-auto rounded-2xl border border-slate-200 dark:border-slate-800"><table className="w-full min-w-[650px] text-left text-sm"><thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-900 dark:text-slate-400"><tr>{headers.map((h) => <th key={h} className="px-5 py-3.5 font-semibold">{h}</th>)}</tr></thead><tbody className="divide-y divide-slate-100 bg-white dark:divide-slate-800 dark:bg-slate-950">{rows.map((row, i) => <tr key={i} className="hover:bg-slate-50/70 dark:hover:bg-slate-900/60">{row.map((cell, j) => <td key={j} className="whitespace-nowrap px-5 py-4 text-slate-700 dark:text-slate-300">{cell}</td>)}</tr>)}</tbody></table></div>;
}

function EmptyActionNotice({ title }) {
  return <div className="mt-5 flex items-start gap-3 rounded-xl border border-teal-200 bg-teal-50/70 p-4 text-sm text-teal-900 dark:border-teal-900 dark:bg-teal-950/40 dark:text-teal-100"><ShieldCheck className="mt-0.5 h-5 w-5 shrink-0" /><div><p className="font-semibold">{title} is a demo preview</p><p className="mt-1 text-teal-800/90 dark:text-teal-200/80">This interaction uses illustrative data only. Sign in to use real workspace features and your own records.</p><Link to="/login" className="mt-2 inline-flex items-center gap-1 font-semibold underline underline-offset-4">Sign in to your workspace <ArrowUpRight className="h-3.5 w-3.5" /></Link></div></div>;
}

export default function PublicDemoDashboard() {
  const [active, setActive] = useState("Overview");
  const [query, setQuery] = useState("");
  const [mobileNav, setMobileNav] = useState(false);
  const [notice, setNotice] = useState("");
  const filteredLeads = useMemo(() => LEADS.filter((lead) => Object.values(lead).join(" ").toLowerCase().includes(query.toLowerCase())), [query]);
  const filteredCampaigns = useMemo(() => CAMPAIGNS.filter((campaign) => Object.values(campaign).join(" ").toLowerCase().includes(query.toLowerCase())), [query]);
  const selectPage = (label) => { setActive(label); setNotice(""); setMobileNav(false); setQuery(""); };

  const primaryAction = (label) => <button onClick={() => setNotice(label)} className="inline-flex items-center gap-2 rounded-xl bg-teal-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-teal-700"><Plus className="h-4 w-4" /> {label}</button>;

  const renderContent = () => {
    if (active === "Overview") return <>
      <SectionTitle eyebrow="Workspace overview" title="Good morning, welcome back" description="A quick snapshot of your sales workspace. All records shown here are sample data." action={<Pill tone="amber">DEMO DATA</Pill>} />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><StatCard label="Total leads" value="1,284" change="+12.8%" icon={Users} /><StatCard label="Active campaigns" value="12" change="+3 this month" icon={Mail} color="violet" /><StatCard label="Open deals" value="$248k" change="+8.2%" icon={BriefcaseBusiness} color="blue" /><StatCard label="Conversion rate" value="16.8%" change="+2.4%" icon={BarChart3} color="amber" /></div>
      <div className="mt-6 grid gap-6 xl:grid-cols-5"><section className="rounded-2xl border border-slate-200 bg-white p-6 dark:border-slate-800 dark:bg-slate-900 xl:col-span-3"><div className="flex items-center justify-between"><div><h2 className="font-bold text-slate-900 dark:text-white">Lead pipeline</h2><p className="mt-1 text-sm text-slate-500">Illustrative distribution by stage</p></div><BarChart3 className="h-5 w-5 text-teal-600" /></div><div className="mt-7 space-y-5">{[["New",82,"bg-sky-500"],["Qualified",66,"bg-teal-500"],["Proposal",43,"bg-violet-500"],["Converted",28,"bg-emerald-500"]].map(([name,n,color])=><div key={name}><div className="mb-2 flex justify-between text-sm"><span className="font-medium">{name}</span><span className="text-slate-500">{n}%</span></div><div className="h-2.5 rounded-full bg-slate-100 dark:bg-slate-800"><div className={`h-full rounded-full ${color}`} style={{width:`${n}%`}} /></div></div>)}</div></section><section className="rounded-2xl border border-slate-200 bg-white p-6 dark:border-slate-800 dark:bg-slate-900 xl:col-span-2"><h2 className="font-bold text-slate-900 dark:text-white">Upcoming activity</h2><p className="mt-1 text-sm text-slate-500">Your sample schedule</p><div className="mt-5 space-y-4">{ACTIVITIES.slice(0,3).map((item)=><div key={item.title} className="flex gap-3"><span className="mt-1 rounded-lg bg-violet-50 p-2 text-violet-700 dark:bg-violet-500/10 dark:text-violet-300"><Clock3 className="h-4 w-4" /></span><div><p className="text-sm font-semibold">{item.title}</p><p className="mt-1 text-xs text-slate-500">{item.detail}</p></div></div>)}</div><button onClick={()=>selectPage("Activities")} className="mt-5 text-sm font-semibold text-teal-700 hover:underline dark:text-teal-300">View all activity →</button></section></div>
      <EmptyActionNotice title="Dashboard actions" />
    </>;
    if (active === "Campaigns") return <><SectionTitle eyebrow="Marketing workspace" title="Campaigns" description="Review sample campaign performance, status, and audiences." action={primaryAction("Create campaign")} /><div className="mb-5 grid gap-4 sm:grid-cols-3"><StatCard label="Total campaigns" value="18" change="+4 this month" icon={Mail} /><StatCard label="Emails delivered" value="24.8k" change="+9.3%" icon={CheckCircle2} color="blue" /><StatCard label="Avg. open rate" value="42.8%" change="+3.1%" icon={Activity} color="violet" /></div><Table headers={["Campaign","Type","Audience","Status","Sent","Open rate"]} rows={filteredCampaigns.map(c=>[<span className="font-semibold text-slate-900 dark:text-white">{c.name}</span>,c.channel,c.audience,<Pill tone={c.status==="Active"?"green":c.status==="Scheduled"?"blue":"gray"}>{c.status}</Pill>,c.sent,c.rate])} /><EmptyActionNotice title={notice || "Create campaign"} /></>;
    if (active === "Leads") return <><SectionTitle eyebrow="Sales workspace" title="Leads" description="Explore a searchable sample lead list. No real contact records are loaded." action={primaryAction("Add lead")} /><div className="mb-4 flex flex-wrap items-center justify-between gap-3"><p className="text-sm text-slate-500">{filteredLeads.length} sample leads</p><div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 dark:border-slate-800 dark:bg-slate-900"><Search className="h-4 w-4 text-slate-400" /><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search sample leads..." className="w-48 bg-transparent text-sm outline-none placeholder:text-slate-400" /></div></div><Table headers={["Lead","Company","Email","Status","Lead score","Source"]} rows={filteredLeads.map(l=>[<span className="font-semibold text-slate-900 dark:text-white">{l.name}</span>,l.company,l.email,<Pill tone={l.status==="Qualified"?"green":l.status==="Contacted"?"blue":"gray"}>{l.status}</Pill>,<span className="font-semibold">{l.score}/100</span>,l.source])} /><EmptyActionNotice title={notice || "Add lead"} /></>;
    if (active === "Deals") return <><SectionTitle eyebrow="Revenue workspace" title="Deals" description="Explore an example sales pipeline and opportunity values." action={primaryAction("Add deal")} /><div className="mb-5 grid gap-4 sm:grid-cols-3"><StatCard label="Pipeline value" value="$100.1k" change="+11.5%" icon={BriefcaseBusiness} /><StatCard label="Open opportunities" value="12" change="3 new" icon={Target} color="violet" /><StatCard label="Win rate" value="38.4%" change="+4.2%" icon={CheckCircle2} color="blue" /></div><Table headers={["Deal","Company","Value","Stage","Probability"]} rows={DEALS.map(d=>[<span className="font-semibold text-slate-900 dark:text-white">{d.name}</span>,d.company,d.value,<Pill tone={d.stage==="Won"?"green":d.stage==="Negotiation"?"violet":"blue"}>{d.stage}</Pill>,d.probability])} /><EmptyActionNotice title={notice || "Add deal"} /></>;
    if (active === "Contacts") return <><SectionTitle eyebrow="Relationship management" title="Contacts" description="A preview of contact management using fictional sample profiles." action={primaryAction("Add contact")} /><Table headers={["Contact","Organization","Email","Relationship","Last activity"]} rows={LEADS.slice(0,4).map((l,i)=>[<span className="font-semibold text-slate-900 dark:text-white">{l.name}</span>,l.company,l.email,<Pill tone={i%2?"blue":"green"}>{i%2?"Customer":"Prospect"}</Pill>,["Today","Yesterday","Oct 14","Oct 13"][i]])} /><EmptyActionNotice title={notice || "Add contact"} /></>;
    if (active === "Activities") return <><SectionTitle eyebrow="Team productivity" title="Activities" description="Example calls, tasks, and campaign events." action={primaryAction("Add activity")} /><div className="space-y-3">{ACTIVITIES.map((a,i)=><article key={a.title} className="flex items-center gap-4 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"><div className="rounded-xl bg-teal-50 p-3 text-teal-700 dark:bg-teal-500/10 dark:text-teal-300"><CalendarDays className="h-5 w-5" /></div><div className="min-w-0 flex-1"><h3 className="font-semibold">{a.title}</h3><p className="mt-1 text-sm text-slate-500">{a.detail}</p></div><Pill tone={i===0?"blue":"gray"}>{a.status}</Pill></article>)}</div><EmptyActionNotice title={notice || "Add activity"} /></>;
    if (active === "Calendar") return <><SectionTitle eyebrow="Planning" title="Calendar" description="A simple sample schedule of upcoming sales activities." action={primaryAction("Schedule event")} /><div className="grid gap-4 sm:grid-cols-2">{ACTIVITIES.map((a,i)=><article key={a.title} className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"><div className="flex items-center justify-between"><Pill tone="violet">{["Today","Today","Tomorrow","Oct 20"][i]}</Pill><CalendarDays className="h-5 w-5 text-teal-600" /></div><h3 className="mt-4 font-bold">{a.title}</h3><p className="mt-2 text-sm text-slate-500">{a.detail}</p></article>)}</div><EmptyActionNotice title={notice || "Schedule event"} /></>;
    if (active === "Analytics") return <><SectionTitle eyebrow="Insights" title="Analytics" description="Sample business performance metrics and trends." action={<Pill tone="amber">Illustrative</Pill>} /><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><StatCard label="New leads" value="1,284" change="+12.8%" icon={Users} /><StatCard label="Conversion" value="16.8%" change="+2.4%" icon={ChartNoAxesCombined} color="violet" /><StatCard label="Revenue" value="$84,250" change="+8.2%" icon={BriefcaseBusiness} color="blue" /><StatCard label="Engagement" value="42.8%" change="+3.1%" icon={Activity} color="amber" /></div><section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 dark:border-slate-800 dark:bg-slate-900"><h2 className="font-bold">Performance by month</h2><p className="mt-1 text-sm text-slate-500">Sample index values, not live account analytics</p><div className="mt-6 flex h-52 items-end gap-3 sm:gap-6">{[38,52,44,68,59,82,72,95,76,88,69,100].map((n,i)=><div key={i} className="flex h-full flex-1 flex-col items-center justify-end gap-2"><div className="w-full max-w-12 rounded-t-lg bg-gradient-to-t from-teal-600 to-cyan-400" style={{height:`${n}%`}} /><span className="text-[10px] text-slate-500">{["N","D","J","F","M","A","M","J","J","A","S","O"][i]}</span></div>)}</div></section></>;
    if (active === "Reports") return <><SectionTitle eyebrow="Insights" title="Reports" description="Preview common report types available in a sales workspace." action={primaryAction("Generate report")} /><div className="grid gap-4 sm:grid-cols-2">{[["Lead conversion report","Lead sources, qualification, and conversion trend",Users],["Campaign performance","Delivery, opens, clicks, and engagement",Mail],["Revenue pipeline","Deal stages and projected revenue",BarChart3],["Team activity","Calls, tasks, and completed follow-ups",Activity]].map(([title,desc,Icon])=><button key={title} onClick={()=>setNotice(title)} className="rounded-2xl border border-slate-200 bg-white p-5 text-left transition hover:border-teal-300 hover:shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:hover:border-teal-700"><span className="inline-flex rounded-xl bg-violet-50 p-3 text-violet-700 dark:bg-violet-500/10 dark:text-violet-300"><Icon className="h-5 w-5" /></span><h3 className="mt-4 font-bold">{title}</h3><p className="mt-2 text-sm leading-6 text-slate-500">{desc}</p><span className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-teal-700 dark:text-teal-300">Preview report <ArrowUpRight className="h-4 w-4" /></span></button>)}</div><EmptyActionNotice title={notice || "Generate report"} /></>;
    return null;
  };

  return <div className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur dark:border-slate-800 dark:bg-slate-950/95"><div className="flex h-16 items-center justify-between gap-3 px-4 sm:px-6"><div className="flex items-center gap-3"><button onClick={()=>setMobileNav(!mobileNav)} className="rounded-lg p-2 hover:bg-slate-100 dark:hover:bg-slate-800 lg:hidden" aria-label="Toggle navigation">{mobileNav?<X className="h-5 w-5"/>:<Menu className="h-5 w-5"/>}</button><Link to="/" className="flex items-center gap-2.5"><span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-teal-500 to-violet-600 text-sm font-black text-white">FT</span><span className="font-bold tracking-tight">FIN-TECH <span className="font-normal text-slate-400">Demo</span></span></Link></div><div className="hidden items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-400 sm:flex dark:border-slate-800 dark:bg-slate-900"><Command className="h-3.5 w-3.5"/> Interactive preview <span className="ml-3"><Pill tone="amber">SAMPLE DATA</Pill></span></div><div className="flex items-center gap-2"><span className="hidden items-center gap-1.5 text-xs font-medium text-slate-500 md:flex"><ShieldCheck className="h-4 w-4 text-emerald-600"/> Read-only</span><Link to="/login" className="rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-800 dark:bg-white dark:text-slate-950 dark:hover:bg-slate-200">Sign in <ArrowUpRight className="ml-1 inline h-4 w-4"/></Link></div></div></header>
    <div className="mx-auto flex max-w-[1600px]">
      <aside className={`${mobileNav?"block":"hidden"} fixed inset-y-16 left-0 z-20 w-64 overflow-y-auto border-r border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950 lg:sticky lg:top-16 lg:block lg:h-[calc(100vh-4rem)] lg:shrink-0`}><div className="mb-4 px-3 text-[11px] font-bold uppercase tracking-[0.16em] text-slate-400">Demo workspace</div>{["Workspace","Insights"].map(section=><div key={section} className="mb-5"><p className="mb-2 px-3 text-xs font-semibold text-slate-400">{section}</p><nav className="space-y-1">{NAV.filter(n=>n.section===section).map(({label,icon:Icon})=><button key={label} onClick={()=>selectPage(label)} className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-medium transition ${active===label?"bg-teal-50 text-teal-800 dark:bg-teal-500/10 dark:text-teal-300":"text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-900"}`}><Icon className="h-[18px] w-[18px]"/>{label}{active===label&&<span className="ml-auto h-1.5 w-1.5 rounded-full bg-teal-600"/>}</button>)}</nav></div>)}<div className="mt-8 rounded-2xl border border-teal-100 bg-teal-50 p-4 dark:border-teal-900 dark:bg-teal-950/30"><Sparkles className="h-5 w-5 text-teal-700 dark:text-teal-300"/><p className="mt-3 text-sm font-bold">Ready for your workspace?</p><p className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">Sign in to manage your real campaigns and records.</p><Link to="/login" className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-teal-800 dark:text-teal-300">Open CRM <ArrowUpRight className="h-3.5 w-3.5"/></Link></div></aside>
      <main className="min-w-0 flex-1 px-4 py-7 sm:px-6 sm:py-9 lg:px-9">{renderContent()}<footer className="mt-10 flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 py-5 text-xs text-slate-500 dark:border-slate-800"><span>FIN-TECH interactive public demo · fictional sample data only</span><span className="inline-flex items-center gap-1"><ShieldCheck className="h-3.5 w-3.5 text-emerald-600"/> Private CRM data remains protected</span></footer></main>
    </div>
  </div>;
}
