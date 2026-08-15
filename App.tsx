import React, { useState, useEffect, useRef } from 'react';

// ==========================================
// 1. УТИЛИТЫ И БАЗОВЫЕ ФУНКЦИИ
// ==========================================

// Жесткое удаление смайликов (оставляем только текст, цифры и базовую пунктуацию)
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
// 2. SVG ИКОНКИ (БЕЗ ВНЕШНИХ ЗАВИСИМОСТЕЙ)
// ==========================================
const Icons = {
  Home: () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-6 h-6"><path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" /></svg>,
  Chat: () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-6 h-6"><path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" /></svg>,
  User: () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-6 h-6"><path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>,
  Search: () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5"><path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>,
  Shield: () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5"><path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg>,
  Warning: () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5"><path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
};

// ==========================================
// 3. ТИПЫ ДАННЫХ И МОКИ
// ==========================================
type Page = 'feed' | 'chat' | 'profile';
type ChatTab = 'global' | 'friends' | 'ai';

interface UserProfile {
  id: string;
  name: string;
  photoUrl: string | null;
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
  },
  {
    id: 3,
    title: "Видеокарта RTX 4090",
    price: 195000,
    platform: "DNS",
    city: "Москва",
    sellerName: "DNS Магазин",
    sellerPhone: "8 (800) 770-79-99",
    isPerekup: false,
    hasAccidents: false,
    owners: 0,
    image: "https://images.unsplash.com/photo-1591488320449-011701bb6704?auto=format&fit=crop&w=400&q=80"
  }
];

// ==========================================
// 4. КОМПОНЕНТ ЛЕНТЫ И ФИЛЬТРОВ (FEED)
// ==========================================
const FeedPage: React.FC = () => {
  const [search, setSearch] = useState("");
  const [city, setCity] = useState("Ульяновск");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");

  return (
    <div className="pb-24 pt-4 px-4 max-w-3xl mx-auto animate-fade-in">
      <h1 className="text-3xl font-extrabold text-gray-900 mb-6 tracking-tight">Поиск товаров</h1>
      
      {/* Панель жестких фильтров */}
      <div className="bg-white p-5 rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-gray-100 mb-8">
        <div className="relative mb-4">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-gray-400">
            <Icons.Search />
          </div>
          <input 
            type="text" 
            placeholder="Что ищем? (Например: MacBook или BMW)"
            className="w-full pl-10 pr-4 py-3 bg-gray-50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all font-medium"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
          <div>
            <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">Город</label>
            <input type="text" value={city} onChange={(e) => setCity(e.target.value)}
              className="w-full p-2.5 bg-gray-50 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 font-medium" />
          </div>
          <div>
            <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">Бюджет от (₽)</label>
            <input type="number" value={minPrice} onChange={(e) => setMinPrice(e.target.value)} placeholder="0"
              className="w-full p-2.5 bg-gray-50 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 font-medium" />
          </div>
          <div>
            <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">Бюджет до (₽)</label>
            <input type="number" value={maxPrice} onChange={(e) => setMaxPrice(e.target.value)} placeholder="Бесконечность"
              className="w-full p-2.5 bg-gray-50 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 font-medium" />
          </div>
        </div>

        <button className="w-full bg-gray-900 hover:bg-black text-white font-bold py-3.5 rounded-xl transition-colors shadow-md">
          Применить фильтры
        </button>
      </div>

      {/* Выдача результатов */}
      <div className="space-y-5">
        {MOCK_LISTINGS.map((item) => (
          <div key={item.id} className="bg-white rounded-2xl overflow-hidden shadow-[0_4px_20px_rgb(0,0,0,0.05)] border border-gray-100 flex flex-col md:flex-row">
            <div className="md:w-2/5 h-48 md:h-auto relative">
              <img src={item.image} alt={item.title} className="w-full h-full object-cover" />
              <div className="absolute top-3 left-3 bg-white/90 backdrop-blur-sm px-2.5 py-1 rounded-md text-xs font-bold text-gray-800 shadow-sm">
                {item.platform}
              </div>
            </div>
            
            <div className="p-5 flex-1 flex flex-col justify-between">
              <div>
                <div className="flex justify-between items-start">
                  <h3 className="text-xl font-bold text-gray-900 leading-tight mb-1">{item.title}</h3>
                </div>
                <p className="text-2xl font-extrabold text-blue-600 mb-3">{item.price.toLocaleString()} ₽</p>
                
                {/* Компромат и плашки */}
                <div className="flex flex-wrap gap-2 mb-4">
                  {item.isPerekup ? (
                    <span className="inline-flex items-center gap-1 bg-red-50 text-red-700 px-2.5 py-1 rounded-md text-xs font-bold border border-red-100">
                      <Icons.Warning /> Перекуп
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 bg-green-50 text-green-700 px-2.5 py-1 rounded-md text-xs font-bold border border-green-100">
                      <Icons.Shield /> Проверенный продавец
                    </span>
                  )}
                  {item.hasAccidents && (
                    <span className="inline-flex items-center gap-1 bg-orange-50 text-orange-700 px-2.5 py-1 rounded-md text-xs font-bold border border-orange-100">
                      Битая (ДТП)
                    </span>
                  )}
                  <span className="bg-gray-100 text-gray-600 px-2.5 py-1 rounded-md text-xs font-bold">
                    Владельцев: {item.owners}
                  </span>
                </div>
              </div>

              {/* Сбор данных о продавце */}
              <div className="bg-gray-50 rounded-xl p-3 border border-gray-100">
                <p className="text-sm text-gray-500 mb-1">Продавец: <span className="font-bold text-gray-900">{item.sellerName}</span></p>
                <p className="text-sm text-gray-500">Контакт: <span className="font-mono bg-white px-2 py-0.5 rounded border border-gray-200 font-bold text-gray-800 tracking-wide">{item.sellerPhone}</span></p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// ==========================================
// 5. КОМПОНЕНТ МЕССЕНДЖЕРА (БЕЗ СМАЙЛОВ)
// ==========================================
const MessengerPage: React.FC<{ user: UserProfile }> = ({ user }) => {
  const [activeTab, setActiveTab] = useState<ChatTab>('global');
  const [inputText, setInputText] = useState("");
  const [friendId, setFriendId] = useState("");
  
  // Раздельные истории для имитации
  const [globalChat, setGlobalChat] = useState<Message[]>([
    { id: 1, sender: "Система", text: "Добро пожаловать в мировой чат. Смайлики запрещены правилами сервера.", timestamp: "12:00", isMine: false }
  ]);
  const [friendsChat, setFriendsChat] = useState<Message[]>([]);
  const [aiChat, setAiChat] = useState<Message[]>([
    { id: 1, sender: "Vision AI", text: "Привет. Я ИИ-ассистент. Отправь мне ссылку на фото или спроси о проверке автомобиля.", timestamp: "12:00", isMine: false }
  ]);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Автоскролл вниз
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [globalChat, friendsChat, aiChat, activeTab]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    // ВАЖНО: Фильтруем смайлики прямо во время печати
    setInputText(stripEmojis(e.target.value));
  };

  const sendMessage = () => {
    const text = inputText.trim();
    if (!text) return;

    const newMessage: Message = {
      id: Date.now(),
      sender: user.name || "Аноним",
      text: text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      isMine: true
    };

    if (activeTab === 'global') {
      setGlobalChat(prev => [...prev, newMessage]);
    } else if (activeTab === 'friends') {
      if (!friendId.trim()) return alert("Сначала введите ID друга сверху!");
      setFriendsChat(prev => [...prev, newMessage]);
    } else if (activeTab === 'ai') {
      setAiChat(prev => [...prev, newMessage]);
      
      // Имитация ответа ИИ
      setTimeout(() => {
        setAiChat(prev => [...prev, {
          id: Date.now() + 1,
          sender: "Vision AI",
          text: `Анализирую ваш запрос: "${text}". Запускаю протокол сбора компромата...`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          isMine: false
        }]);
      }, 1000);
    }

    setInputText("");
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') sendMessage();
  };

  const currentMessages = activeTab === 'global' ? globalChat : activeTab === 'friends' ? friendsChat : aiChat;

  return (
    <div className="h-screen flex flex-col bg-gray-50 pb-16">
      {/* Шапка чата */}
      <div className="bg-white border-b border-gray-200 px-4 py-4 pt-6 shadow-sm z-10">
        <h1 className="text-2xl font-extrabold text-gray-900 mb-4">Мессенджеры</h1>
        <div className="flex bg-gray-100 p-1 rounded-xl">
          <button 
            onClick={() => setActiveTab('global')}
            className={`flex-1 py-2 text-sm font-bold rounded-lg transition-all ${activeTab === 'global' ? 'bg-white text-blue-600 shadow-sm' : 'text-gray-500 hover:text-gray-900'}`}
          >
            Всемирный
          </button>
          <button 
            onClick={() => setActiveTab('friends')}
            className={`flex-1 py-2 text-sm font-bold rounded-lg transition-all ${activeTab === 'friends' ? 'bg-white text-blue-600 shadow-sm' : 'text-gray-500 hover:text-gray-900'}`}
          >
            С друзьями
          </button>
          <button 
            onClick={() => setActiveTab('ai')}
            className={`flex-1 py-2 text-sm font-bold rounded-lg transition-all ${activeTab === 'ai' ? 'bg-white text-blue-600 shadow-sm' : 'text-gray-500 hover:text-gray-900'}`}
          >
            Чат с AI
          </button>
        </div>
      </div>

      {/* Поле ID для друзей */}
      {activeTab === 'friends' && (
        <div className="bg-white border-b border-gray-200 px-4 py-3 flex gap-2 items-center">
          <span className="text-sm font-bold text-gray-500">Кому:</span>
          <input 
            type="text" 
            placeholder="Введите ID (Например: ID-X7B9A)"
            value={friendId}
            onChange={(e) => setFriendId(e.target.value.toUpperCase())}
            className="flex-1 bg-gray-50 border border-gray-200 rounded-lg px-3 py-1.5 text-sm font-mono focus:outline-none focus:border-blue-500"
          />
        </div>
      )}

      {/* Область сообщений */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {currentMessages.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <p className="text-gray-400 font-medium text-center">
              Здесь пока нет сообщений.<br/>Смайлики автоматически удаляются.
            </p>
          </div>
        ) : (
          currentMessages.map((msg) => (
            <div key={msg.id} className={`flex flex-col ${msg.isMine ? 'items-end' : 'items-start'}`}>
              <span className="text-[10px] font-bold text-gray-400 mb-1 ml-1">
                {msg.sender} • {msg.timestamp}
              </span>
              <div className={`max-w-[80%] px-4 py-2.5 rounded-2xl ${
                msg.isMine 
                  ? 'bg-blue-600 text-white rounded-tr-sm' 
                  : msg.sender === 'Vision AI' 
                    ? 'bg-gray-900 text-white rounded-tl-sm'
                    : 'bg-white border border-gray-200 text-gray-800 rounded-tl-sm shadow-sm'
              }`}>
                <p className="text-[15px] leading-relaxed break-words">{msg.text}</p>
              </div>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Инпут */}
      <div className="bg-white border-t border-gray-200 p-4 pb-6">
        <div className="flex gap-2 max-w-3xl mx-auto">
          <input 
            type="text"
            value={inputText}
            onChange={handleInputChange}
            onKeyPress={handleKeyPress}
            placeholder="Сообщение (без смайликов)..."
            className="flex-1 bg-gray-50 border border-gray-200 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all font-medium"
          />
          <button 
            onClick={sendMessage}
            disabled={!inputText.trim()}
            className="bg-blue-600 disabled:bg-blue-300 hover:bg-blue-700 text-white rounded-xl px-6 font-bold transition-colors shadow-sm"
          >
            Отправить
          </button>
        </div>
      </div>
    </div>
  );
};

// ==========================================
// 6. КОМПОНЕНТ ПРОФИЛЯ
// ==========================================
const ProfilePage: React.FC<{ user: UserProfile, updateUser: (u: Partial<UserProfile>) => void }> = ({ user, updateUser }) => {
  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    // Убираем смайлы из имени
    updateUser({ name: stripEmojis(e.target.value) });
  };

  const handlePhotoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    // Имитация загрузки фото через создание локального URL
    if (e.target.files && e.target.files[0]) {
      const url = URL.createObjectURL(e.target.files[0]);
      updateUser({ photoUrl: url });
    }
  };

  return (
    <div className="p-4 pt-8 max-w-lg mx-auto animate-fade-in">
      <h1 className="text-3xl font-extrabold text-gray-900 mb-8 text-center">Профиль</h1>

      <div className="bg-white rounded-3xl p-8 shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-gray-100 flex flex-col items-center">
        
        {/* Аватарка */}
        <div className="relative mb-6">
          <div className="w-32 h-32 rounded-full border-4 border-gray-50 bg-gray-100 overflow-hidden shadow-inner flex items-center justify-center">
            {user.photoUrl ? (
              <img src={user.photoUrl} alt="Avatar" className="w-full h-full object-cover" />
            ) : (
              <Icons.User />
            )}
          </div>
          <label className="absolute bottom-0 right-0 bg-blue-600 hover:bg-blue-700 text-white p-2.5 rounded-full cursor-pointer shadow-lg transition-transform hover:scale-105">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4"/></svg>
            <input type="file" accept="image/*" className="hidden" onChange={handlePhotoUpload} />
          </label>
        </div>

        {/* Форма данных */}
        <div className="w-full space-y-5">
          <div>
            <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1.5 ml-1">
              Ваш персональный ID
            </label>
            <div className="w-full bg-gray-50 border border-gray-200 text-gray-900 rounded-xl px-4 py-3 font-mono font-bold text-center text-lg tracking-widest cursor-copy" title="Нажмите, чтобы скопировать">
              {user.id}
            </div>
            <p className="text-xs text-center text-gray-400 mt-2 font-medium">Дайте этот ID друзьям, чтобы общаться в чате</p>
          </div>

          <div>
            <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1.5 ml-1">
              Отображаемое Имя
            </label>
            <input 
              type="text" 
              value={user.name} 
              onChange={handleNameChange}
              placeholder="Введите имя (без смайлов)"
              className="w-full bg-white border border-gray-300 rounded-xl px-4 py-3 font-bold text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all text-center"
            />
          </div>
        </div>

      </div>
    </div>
  );
};

// ==========================================
// 7. ГЛАВНЫЙ ОРКЕСТРАТОР (КОНТЕЙНЕР ПРИЛОЖЕНИЯ)
// ==========================================
export default function App() {
  const [currentPage, setCurrentPage] = useState<Page>('feed');
  const [user, setUser] = useState<UserProfile>(() => {
    // Восстановление профиля из LocalStorage
    const saved = localStorage.getItem('mv_user_profile');
    if (saved) return JSON.parse(saved);
    return { id: generateUserId(), name: '', photoUrl: null };
  });

  useEffect(() => {
    localStorage.setItem('mv_user_profile', JSON.stringify(user));
  }, [user]);

  const updateUser = (updates: Partial<UserProfile>) => {
    setUser(prev => ({ ...prev, ...updates }));
  };

  return (
    <div className="min-h-screen bg-gray-50 font-sans text-gray-900 selection:bg-blue-200">
      
      {/* Динамический рендеринг активной страницы */}
      <main className="w-full h-full">
        {currentPage === 'feed' && <FeedPage />}
        {currentPage === 'chat' && <MessengerPage user={user} />}
        {currentPage === 'profile' && <ProfilePage user={user} updateUser={updateUser} />}
      </main>

      {/* Нижняя навигационная панель (Bottom Navigation Bar) */}
      <nav className="fixed bottom-0 w-full bg-white/90 backdrop-blur-md border-t border-gray-200 pb-safe z-50">
        <div className="flex justify-around items-center h-16 max-w-md mx-auto px-2">
          
          <button 
            onClick={() => setCurrentPage('feed')}
            className={`flex flex-col items-center justify-center w-full h-full space-y-1 transition-colors ${currentPage === 'feed' ? 'text-blue-600' : 'text-gray-400 hover:text-gray-600'}`}
          >
            <Icons.Home />
            <span className="text-[10px] font-bold tracking-wide">ПОИСК</span>
          </button>

          <button 
            onClick={() => setCurrentPage('chat')}
            className={`flex flex-col items-center justify-center w-full h-full space-y-1 transition-colors ${currentPage === 'chat' ? 'text-blue-600' : 'text-gray-400 hover:text-gray-600'}`}
          >
            <div className="relative">
              <Icons.Chat />
              <span className="absolute -top-1 -right-1 bg-red-500 w-2.5 h-2.5 rounded-full border-2 border-white"></span>
            </div>
            <span className="text-[10px] font-bold tracking-wide">ЧАТЫ</span>
          </button>

          <button 
            onClick={() => setCurrentPage('profile')}
            className={`flex flex-col items-center justify-center w-full h-full space-y-1 transition-colors ${currentPage === 'profile' ? 'text-blue-600' : 'text-gray-400 hover:text-gray-600'}`}
          >
            <Icons.User />
            <span className="text-[10px] font-bold tracking-wide">ПРОФИЛЬ</span>
          </button>

        </div>
      </nav>
    </div>
  );
}
