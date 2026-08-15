import React, { useState, useEffect, useRef } from 'react';

// ==========================================
// 1. УТИЛИТЫ И БАЗОВЫЕ ФУНКЦИИ
// ==========================================

const stripEmojis = (text: string) => {
  return text.replace(/[^\w\s.,!?"'а-яА-ЯёЁa-zA-Z0-9-()]/g, '');
};

const generateUserId = () => {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  let id = 'ID-';
  for (let i = 0; i < 6; i++) id += chars.charAt(Math.floor(Math.random() * chars.length));
  return id;
};

// ==========================================
// 2. SVG ИКОНКИ ДЛЯ 5 ВКЛАДОК
// ==========================================
const Icons = {
  Search: () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-6 h-6"><path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>,
  Tracker: () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-6 h-6"><path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" /></svg>,
  Chat: () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-6 h-6"><path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" /></svg>,
  Eye: () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-6 h-6"><path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>,
  User: () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-6 h-6"><path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>,
  Shield: () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4"><path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg>,
  Warning: () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4"><path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
};

// ==========================================
// 3. ТИПЫ ДАННЫХ И СОСТОЯНИЯ
// ==========================================
type Page = 'search' | 'tracker' | 'chat' | 'ivizion' | 'profile';
type ChatTab = 'global' | 'friends' | 'ai';

interface UserProfile {
  id: string;
  name: string;
  photoUrl: string | null;
  apiKey: string;
  serverUrl: string;
}

interface Message {
  id: number;
  sender: string;
  text: string;
  timestamp: string;
  isMine: boolean;
}

const MOCK_LISTINGS = [
  {
    id: 1,
    title: "Toyota Camry 2.5 AT, 2021",
    price: 3200000,
    platform: "Avito",
    city: "Ульяновск",
    sellerName: "Иван Иванов",
    sellerPhone: "+7 (999) 123-45-67",
    isPerekup: true,
    hasAccidents: true,
    owners: 4,
    image: "https://images.unsplash.com/photo-1621007947382-bb3c3994e3fd?auto=format&fit=crop&w=400&q=80"
  },
  {
    id: 2,
    title: "Apple MacBook Pro 16 M2 Max",
    price: 280000,
    platform: "Avito",
    city: "Ульяновск",
    sellerName: "TechStore",
    sellerPhone: "+7 (800) 555-35-35",
    isPerekup: false,
    hasAccidents: false,
    owners: 1,
    image: "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?auto=format&fit=crop&w=400&q=80"
  }
];

const MOCK_TRACKED_ITEMS = [
  {
    id: 101,
    title: "Sony PlayStation 5",
    initialPrice: 55000,
    currentPrice: 49990,
    status: "dropped", // dropped, stable, increased
    lastUpdate: "Сегодня в 14:30",
    platform: "Ozon",
    image: "https://images.unsplash.com/photo-1606813907291-d86efa9b94db?auto=format&fit=crop&w=400&q=80"
  },
  {
    id: 102,
    title: "BMW X5 3.0d, 2019",
    initialPrice: 5500000,
    currentPrice: 5500000,
    status: "stable",
    lastUpdate: "Вчера",
    platform: "Auto.ru",
    image: "https://images.unsplash.com/photo-1555215695-3004980ad54e?auto=format&fit=crop&w=400&q=80"
  }
];

// ==========================================
// 4. ВКЛАДКА 1: ПОИСК (STRICT SCANNER)
// ==========================================
const SearchPage: React.FC = () => {
  const [search, setSearch] = useState("");
  const [city, setCity] = useState("Ульяновск");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [strictMode, setStrictMode] = useState(true);

  return (
    <div className="pb-24 pt-4 px-4 max-w-3xl mx-auto animate-fade-in">
      <h1 className="text-3xl font-extrabold text-gray-900 mb-6 tracking-tight">OSINT Терминал</h1>
      
      <div className="bg-white p-5 rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-gray-100 mb-8">
        <div className="relative mb-4">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-gray-400">
            <Icons.Search />
          </div>
          <input 
            type="text" 
            placeholder="Целевой запрос (Например: MacBook M1)"
            className="w-full pl-10 pr-4 py-3 bg-gray-50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all font-medium"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
          <div>
            <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Город</label>
            <input type="text" value={city} onChange={(e) => setCity(e.target.value)} className="w-full p-2.5 bg-gray-50 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 font-medium" />
          </div>
          <div>
            <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Бюджет от (₽)</label>
            <input type="number" value={minPrice} onChange={(e) => setMinPrice(e.target.value)} placeholder="0" className="w-full p-2.5 bg-gray-50 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 font-medium" />
          </div>
          <div>
            <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Бюджет до (₽)</label>
            <input type="number" value={maxPrice} onChange={(e) => setMaxPrice(e.target.value)} placeholder="∞" className="w-full p-2.5 bg-gray-50 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 font-medium" />
          </div>
        </div>

        {/* Переключатель Strict Mode */}
        <div className="mb-6 bg-red-50 border border-red-100 rounded-xl p-4 flex items-start gap-3">
          <input type="checkbox" checked={strictMode} onChange={() => setStrictMode(!strictMode)} className="mt-1 w-4 h-4 text-red-600 rounded" />
          <div>
            <p className="text-sm font-bold text-red-800 uppercase tracking-wide">STRICT MODE (Убийца автоподбора)</p>
            <p className="text-xs text-red-600 mt-1">Отсеять все сомнительные объявления, перекупов и битые машины. Оставить только 100% совпадения.</p>
          </div>
        </div>

        <button className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3.5 rounded-xl transition-colors shadow-md">
          Инициализировать Парсинг
        </button>
      </div>

      <div className="space-y-5">
        <h2 className="text-lg font-bold text-gray-800">Выдача (Прошли фильтр)</h2>
        {MOCK_LISTINGS.map((item) => (
          <div key={item.id} className="bg-white rounded-2xl overflow-hidden shadow-sm border border-gray-100 flex flex-col md:flex-row">
            <div className="md:w-2/5 h-48 md:h-auto relative">
              <img src={item.image} alt={item.title} className="w-full h-full object-cover" />
              <div className="absolute top-3 left-3 bg-white/90 px-2 py-1 rounded text-xs font-bold text-gray-800">{item.platform}</div>
            </div>
            
            <div className="p-4 flex-1 flex flex-col justify-between">
              <div>
                <h3 className="text-xl font-bold text-gray-900 mb-1">{item.title}</h3>
                <p className="text-2xl font-extrabold text-blue-600 mb-3">{item.price.toLocaleString()} ₽</p>
                <div className="flex flex-wrap gap-2 mb-3">
                  {item.isPerekup ? (
                    <span className="inline-flex items-center gap-1 bg-red-50 text-red-700 px-2 py-1 rounded text-[10px] font-bold border border-red-100"><Icons.Warning /> ПЕРЕКУП</span>
                  ) : (
                    <span className="inline-flex items-center gap-1 bg-green-50 text-green-700 px-2 py-1 rounded text-[10px] font-bold border border-green-100"><Icons.Shield /> ЧАСТНИК</span>
                  )}
                </div>
              </div>
              <button className="w-full bg-gray-100 hover:bg-gray-200 text-gray-800 text-sm font-bold py-2 rounded-lg transition-colors" onClick={() => alert('Добавлено в трекер!')}>
                Взять на трекинг
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// ==========================================
// 5. ВКЛАДКА 2: ТРЕКЕР (ИСТОРИЯ ЦЕН И ПУШИ)
// ==========================================
const TrackerPage: React.FC = () => {
  return (
    <div className="pb-24 pt-4 px-4 max-w-3xl mx-auto animate-fade-in">
      <h1 className="text-3xl font-extrabold text-gray-900 mb-6 tracking-tight">Трекер целей</h1>
      
      <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 mb-6">
        <p className="text-sm text-blue-800">
          Сюда попадают товары, которые прошли жесткий фильтр. Движок опрашивает площадки каждые 15 минут. Если цена упадет — вы получите PUSH.
        </p>
      </div>

      <div className="space-y-4">
        {MOCK_TRACKED_ITEMS.map((item) => (
          <div key={item.id} className="bg-white rounded-2xl p-4 border border-gray-100 shadow-sm flex items-center gap-4">
            <img src={item.image} alt={item.title} className="w-20 h-20 rounded-xl object-cover" />
            <div className="flex-1">
              <h4 className="font-bold text-gray-900 text-sm md:text-base">{item.title}</h4>
              <p className="text-xs text-gray-400 mb-1">{item.platform} • {item.lastUpdate}</p>
              
              <div className="flex items-end gap-2">
                <span className={`text-lg font-bold ${item.status === 'dropped' ? 'text-green-600' : 'text-gray-900'}`}>
                  {item.currentPrice.toLocaleString()} ₽
                </span>
                {item.status === 'dropped' && (
                  <span className="text-xs text-green-500 font-bold mb-1 line-through">
                    {item.initialPrice.toLocaleString()} ₽
                  </span>
                )}
              </div>
            </div>
            
            <div className="flex flex-col gap-2">
              <button className="bg-red-50 text-red-500 hover:bg-red-100 p-2 rounded-lg transition-colors">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5"><path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// ==========================================
// 6. ВКЛАДКА 3: МЕССЕНДЖЕР (P2P И AI)
// ==========================================
const MessengerPage: React.FC<{ user: UserProfile }> = ({ user }) => {
  const [activeTab, setActiveTab] = useState<ChatTab>('global');
  const [inputText, setInputText] = useState("");
  const [globalChat, setGlobalChat] = useState<Message[]>([
    { id: 1, sender: "Система", text: "Смайлики запрещены правилами сервера.", timestamp: "12:00", isMine: false }
  ]);
  const [aiChat, setAiChat] = useState<Message[]>([
    { id: 1, sender: "Vision AI", text: "Я ИИ-ассистент OmniScan. Жду команд.", timestamp: "12:00", isMine: false }
  ]);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [globalChat, aiChat, activeTab]);

  const sendMessage = () => {
    const text = inputText.trim();
    if (!text) return;

    const newMessage: Message = { id: Date.now(), sender: user.name || "Аноним", text, timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }), isMine: true };

    if (activeTab === 'global') {
      setGlobalChat(prev => [...prev, newMessage]);
    } else if (activeTab === 'ai') {
      setAiChat(prev => [...prev, newMessage]);
      setTimeout(() => {
        setAiChat(prev => [...prev, { id: Date.now() + 1, sender: "Vision AI", text: `Обрабатываю: "${text}"...`, timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }), isMine: false }]);
      }, 1000);
    }
    setInputText("");
  };

  const currentMessages = activeTab === 'global' ? globalChat : aiChat;

  return (
    <div className="h-full flex flex-col bg-gray-50 pb-20">
      <div className="bg-white border-b border-gray-200 px-4 py-4 pt-6 shadow-sm z-10">
        <h1 className="text-2xl font-extrabold text-gray-900 mb-4">Мессенджеры</h1>
        <div className="flex bg-gray-100 p-1 rounded-xl">
          <button onClick={() => setActiveTab('global')} className={`flex-1 py-2 text-sm font-bold rounded-lg transition-all ${activeTab === 'global' ? 'bg-white text-blue-600 shadow-sm' : 'text-gray-500'}`}>Global P2P</button>
          <button onClick={() => setActiveTab('ai')} className={`flex-1 py-2 text-sm font-bold rounded-lg transition-all ${activeTab === 'ai' ? 'bg-white text-blue-600 shadow-sm' : 'text-gray-500'}`}>Vision AI</button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {currentMessages.map((msg) => (
          <div key={msg.id} className={`flex flex-col ${msg.isMine ? 'items-end' : 'items-start'}`}>
            <span className="text-[10px] font-bold text-gray-400 mb-1 ml-1">{msg.sender} • {msg.timestamp}</span>
            <div className={`max-w-[80%] px-4 py-2.5 rounded-2xl ${msg.isMine ? 'bg-blue-600 text-white rounded-tr-sm' : 'bg-white border border-gray-200 text-gray-800 rounded-tl-sm shadow-sm'}`}>
              <p className="text-[15px] leading-relaxed break-words">{msg.text}</p>
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="bg-white border-t border-gray-200 p-4">
        <div className="flex gap-2 max-w-3xl mx-auto">
          <input type="text" value={inputText} onChange={(e) => setInputText(stripEmojis(e.target.value))} onKeyPress={(e) => e.key === 'Enter' && sendMessage()} placeholder="Сообщение (без смайлов)..." className="flex-1 bg-gray-50 border border-gray-200 rounded-xl px-4 py-3 focus:outline-none focus:border-blue-500 font-medium" />
          <button onClick={sendMessage} disabled={!inputText.trim()} className="bg-blue-600 disabled:bg-blue-300 hover:bg-blue-700 text-white rounded-xl px-6 font-bold shadow-sm">Отправить</button>
        </div>
      </div>
    </div>
  );
};

// ==========================================
// 7. ВКЛАДКА 4: iVIZION (АНАЛИЗАТОР ФОТО)
// ==========================================
const IVizionPage: React.FC = () => {
  const [photoUrl, setPhotoUrl] = useState("");
  const [isScanning, setIsScanning] = useState(false);
  const [result, setResult] = useState<any>(null);

  const startScan = () => {
    if (!photoUrl) return alert("Вставьте ссылку на фото!");
    setIsScanning(true);
    setResult(null);
    
    // Эмуляция работы локальной Ollama LLaVA
    setTimeout(() => {
      setIsScanning(false);
      setResult({
        is_approved: false,
        critical_defects: ["Несовпадение зазоров капота", "Следы перекраски правого крыла", "Затертый руль (пробег скручен)"],
        summary: "Автомобиль имеет явные признаки скрытого ДТП. Категорически не рекомендуется к покупке без толщиномера."
      });
    }, 2500);
  };

  return (
    <div className="pb-24 pt-4 px-4 max-w-3xl mx-auto animate-fade-in">
      <h1 className="text-3xl font-extrabold text-gray-900 mb-2 tracking-tight">iVizion Engine</h1>
      <p className="text-sm text-gray-500 mb-6">Мультимодальный анализ фотографий товаров через нейросеть для поиска скрытых дефектов.</p>
      
      <div className="bg-white p-5 rounded-2xl shadow-sm border border-gray-100 mb-6">
        <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Ссылка на фото с маркетплейса</label>
        <div className="flex gap-2">
          <input 
            type="text" 
            placeholder="https://..." 
            className="flex-1 bg-gray-50 border border-gray-200 rounded-xl px-4 py-3 font-medium focus:border-blue-500"
            value={photoUrl}
            onChange={(e) => setPhotoUrl(e.target.value)}
          />
          <button 
            onClick={startScan}
            disabled={isScanning}
            className="bg-gray-900 hover:bg-black text-white px-6 rounded-xl font-bold transition-colors disabled:opacity-50"
          >
            Скан
          </button>
        </div>

        {photoUrl && (
          <div className="mt-4 relative h-48 bg-gray-100 rounded-xl overflow-hidden border border-gray-200">
            <img src={photoUrl} alt="Target" className="w-full h-full object-cover" />
            {isScanning && (
              <div className="absolute inset-0 bg-blue-600/20 backdrop-blur-sm flex items-center justify-center">
                <div className="text-white font-bold tracking-widest animate-pulse">Анализ LLaVA Vision...</div>
              </div>
            )}
          </div>
        )}
      </div>

      {result && (
        <div className="bg-white rounded-2xl p-5 border border-red-200 shadow-sm relative overflow-hidden">
          <div className="absolute top-0 right-0 bg-red-500 text-white text-[10px] font-bold px-3 py-1 rounded-bl-lg">ОТБРАКОВКА</div>
          <h3 className="text-lg font-bold text-gray-900 mb-3">Отчет нейросети</h3>
          <ul className="list-disc pl-5 text-sm text-red-600 font-medium space-y-1 mb-4">
            {result.critical_defects.map((def: string, i: number) => <li key={i}>{def}</li>)}
          </ul>
          <div className="bg-gray-50 p-3 rounded-lg border border-gray-200">
            <p className="text-sm font-bold text-gray-700">Вердикт:</p>
            <p className="text-sm text-gray-600">{result.summary}</p>
          </div>
        </div>
      )}
    </div>
  );
};

// ==========================================
// 8. ВКЛАДКА 5: ПРОФИЛЬ И НАСТРОЙКИ
// ==========================================
const ProfilePage: React.FC<{ user: UserProfile, updateUser: (u: Partial<UserProfile>) => void }> = ({ user, updateUser }) => {
  return (
    <div className="pb-24 pt-4 px-4 max-w-lg mx-auto animate-fade-in">
      <h1 className="text-3xl font-extrabold text-gray-900 mb-6 text-center">Профиль</h1>

      <div className="bg-white rounded-3xl p-6 shadow-sm border border-gray-100 space-y-6">
        <div>
          <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Ваш ID (для чата)</label>
          <div className="w-full bg-gray-50 border border-gray-200 rounded-xl px-4 py-3 font-mono font-bold text-center text-lg">{user.id}</div>
        </div>

        <div>
          <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Имя</label>
          <input type="text" value={user.name} onChange={(e) => updateUser({ name: stripEmojis(e.target.value) })} placeholder="Без смайлов" className="w-full bg-white border border-gray-300 rounded-xl px-4 py-3 font-bold text-center focus:border-blue-500" />
        </div>

        <div className="border-t border-gray-100 pt-6 space-y-4">
          <h3 className="font-bold text-gray-900">Настройки Backend API</h3>
          <div>
            <label className="block text-xs text-gray-500 mb-1">IP сервера OmniScan</label>
            <input type="text" value={user.serverUrl} onChange={(e) => updateUser({ serverUrl: e.target.value })} className="w-full border border-gray-300 rounded-lg px-3 py-2 font-mono text-sm focus:border-blue-500" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Секретный API-ключ</label>
            <input type="password" value={user.apiKey} onChange={(e) => updateUser({ apiKey: e.target.value })} className="w-full border border-gray-300 rounded-lg px-3 py-2 font-mono text-sm focus:border-blue-500" />
          </div>
          <button className="w-full bg-gray-900 text-white font-bold py-3 rounded-xl hover:bg-black transition-colors" onClick={() => alert('Конфигурация сохранена!')}>
            Сохранить настройки
          </button>
        </div>
      </div>
    </div>
  );
};

// ==========================================
// 9. ГЛАВНЫЙ ОРКЕСТРАТОР ПРИЛОЖЕНИЯ
// ==========================================
export default function App() {
  const [currentPage, setCurrentPage] = useState<Page>('search');
  const [user, setUser] = useState<UserProfile>(() => {
    const saved = localStorage.getItem('mv_user_profile');
    if (saved) return JSON.parse(saved);
    return { id: generateUserId(), name: '', photoUrl: null, apiKey: '', serverUrl: 'http://localhost:8000' };
  });

  useEffect(() => {
    localStorage.setItem('mv_user_profile', JSON.stringify(user));
  }, [user]);

  const updateUser = (updates: Partial<UserProfile>) => setUser(prev => ({ ...prev, ...updates }));

  return (
    <div className="min-h-screen bg-gray-50 font-sans text-gray-900">
      
      <main className="w-full h-full">
        {currentPage === 'search' && <SearchPage />}
        {currentPage === 'tracker' && <TrackerPage />}
        {currentPage === 'chat' && <MessengerPage user={user} />}
        {currentPage === 'ivizion' && <IVizionPage />}
        {currentPage === 'profile' && <ProfilePage user={user} updateUser={updateUser} />}
      </main>

      {/* НИЖНЯЯ ПАНЕЛЬ С 5 ВКЛАДКАМИ */}
      <nav className="fixed bottom-0 w-full bg-white/90 backdrop-blur-md border-t border-gray-200 pb-safe z-50">
        <div className="flex justify-around items-center h-16 max-w-md mx-auto px-1">
          
          <button onClick={() => setCurrentPage('search')} className={`flex flex-col items-center justify-center w-full h-full space-y-1 ${currentPage === 'search' ? 'text-blue-600' : 'text-gray-400 hover:text-gray-600'}`}>
            <Icons.Search />
            <span className="text-[9px] font-bold tracking-wider">СКАНЕР</span>
          </button>

          <button onClick={() => setCurrentPage('tracker')} className={`flex flex-col items-center justify-center w-full h-full space-y-1 ${currentPage === 'tracker' ? 'text-blue-600' : 'text-gray-400 hover:text-gray-600'}`}>
            <Icons.Tracker />
            <span className="text-[9px] font-bold tracking-wider">ТРЕКЕР</span>
          </button>

          <button onClick={() => setCurrentPage('chat')} className={`flex flex-col items-center justify-center w-full h-full space-y-1 ${currentPage === 'chat' ? 'text-blue-600' : 'text-gray-400 hover:text-gray-600'}`}>
            <div className="relative">
              <Icons.Chat />
              <span className="absolute -top-1 -right-1 bg-red-500 w-2 h-2 rounded-full border border-white"></span>
            </div>
            <span className="text-[9px] font-bold tracking-wider">ЧАТ</span>
          </button>

          <button onClick={() => setCurrentPage('ivizion')} className={`flex flex-col items-center justify-center w-full h-full space-y-1 ${currentPage === 'ivizion' ? 'text-blue-600' : 'text-gray-400 hover:text-gray-600'}`}>
            <Icons.Eye />
            <span className="text-[9px] font-bold tracking-wider">IVIZION</span>
          </button>

          <button onClick={() => setCurrentPage('profile')} className={`flex flex-col items-center justify-center w-full h-full space-y-1 ${currentPage === 'profile' ? 'text-blue-600' : 'text-gray-400 hover:text-gray-600'}`}>
            <Icons.User />
            <span className="text-[9px] font-bold tracking-wider">ПРОФИЛЬ</span>
          </button>

        </div>
      </nav>
    </div>
  );
}
