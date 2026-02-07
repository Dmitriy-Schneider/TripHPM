// Глобальные переменные
const API_URL = window.location.origin;
let authToken = localStorage.getItem('authToken');
let currentUser = null;
let currentTripId = null;
let allTrips = [];

// ========== СИСТЕМА ЛОГИРОВАНИЯ ==========

// Отправка логов на сервер
async function logToServer(level, message, context = null) {
    try {
        const logData = {
            level: level,
            message: message,
            context: context,
            url: window.location.href,
            user_agent: navigator.userAgent
        };

        await fetch(`${API_URL}/logs/log`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': authToken ? `Bearer ${authToken}` : ''
            },
            body: JSON.stringify(logData)
        });
    } catch (error) {
        // Если не можем отправить лог - не падаем
        console.error('Failed to send log to server:', error);
    }
}

// Обертки для логирования
const logger = {
    info: (message, context) => {
        console.log(`[INFO] ${message}`, context || '');
        logToServer('info', message, context);
    },
    warn: (message, context) => {
        console.warn(`[WARN] ${message}`, context || '');
        logToServer('warn', message, context);
    },
    error: (message, context) => {
        console.error(`[ERROR] ${message}`, context || '');
        logToServer('error', message, context);
    },
    debug: (message, context) => {
        console.debug(`[DEBUG] ${message}`, context || '');
        logToServer('debug', message, context);
    }
};

// Глобальная обработка ошибок
window.addEventListener('error', (event) => {
    logger.error('Uncaught error', {
        message: event.message,
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno
    });
});

window.addEventListener('unhandledrejection', (event) => {
    logger.error('Unhandled promise rejection', {
        reason: event.reason?.toString()
    });
});

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', () => {
    if (authToken) {
        checkAuth();
    } else {
        showAuth();
    }

    // Инициализируем умный выбор дат
    initSmartDatePickers();

    const receiptCategory = document.getElementById('receiptCategory');
    const receiptCategoryCustomGroup = document.getElementById('receiptCategoryCustomGroup');
    const editReceiptCategory = document.getElementById('editReceiptCategory');
    const editReceiptCategoryCustomGroup = document.getElementById('editReceiptCategoryCustomGroup');

    if (receiptCategory) {
        toggleCustomCategory(receiptCategory, receiptCategoryCustomGroup);
        receiptCategory.addEventListener('change', () => {
            toggleCustomCategory(receiptCategory, receiptCategoryCustomGroup);
        });
    }

    if (editReceiptCategory) {
        toggleCustomCategory(editReceiptCategory, editReceiptCategoryCustomGroup);
        editReceiptCategory.addEventListener('change', () => {
            toggleCustomCategory(editReceiptCategory, editReceiptCategoryCustomGroup);
        });
    }

    const filterCity = document.getElementById('filterCity');
    const filterOrg = document.getElementById('filterOrg');
    const filterDateFrom = document.getElementById('filterDateFrom');
    const filterDateTo = document.getElementById('filterDateTo');

    [filterCity, filterOrg].forEach((el) => {
        if (el) {
            el.addEventListener('input', applyTripFilters);
        }
    });
    [filterDateFrom, filterDateTo].forEach((el) => {
        if (el) {
            el.addEventListener('change', applyTripFilters);
        }
    });
});

// Проверка авторизации
async function checkAuth() {
    try {
        const response = await fetch(`${API_URL}/users/me`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            currentUser = await response.json();
            showMain();
            loadTrips();
        } else {
            showAuth();
        }
    } catch (error) {
        console.error('Auth error:', error);
        showAuth();
    }
}

// Переключение табов
function switchTab(tab) {
    const loginForm = document.getElementById('loginForm');
    const registerForm = document.getElementById('registerForm');
    const tabs = document.querySelectorAll('.tab');

    tabs.forEach(t => t.classList.remove('active'));

    if (tab === 'login') {
        loginForm.style.display = 'block';
        registerForm.style.display = 'none';
        tabs[0].classList.add('active');
    } else {
        loginForm.style.display = 'none';
        registerForm.style.display = 'block';
        tabs[1].classList.add('active');
    }
}

// Обработка входа
async function handleLogin(event) {
    event.preventDefault();

    const username = document.getElementById('loginUsername').value;
    const password = document.getElementById('loginPassword').value;

    try {
        const formData = new FormData();
        formData.append('username', username);
        formData.append('password', password);

        const response = await fetch(`${API_URL}/auth/login`, {
            method: 'POST',
            body: formData
        });

        if (response.ok) {
            const data = await response.json();
            authToken = data.access_token;
            localStorage.setItem('authToken', authToken);
            await checkAuth();
            showNotification('Вход выполнен успешно', 'success');
        } else {
            const error = await response.json();
            showError(error.detail || 'Ошибка входа');
        }
    } catch (error) {
        console.error('Login error:', error);
        showError('Ошибка соединения с сервером');
    }
}

// Быстрый вход для тестирования
async function quickTestLogin() {
    // Заполняем поля и отправляем форму
    document.getElementById('loginUsername').value = 'test';
    document.getElementById('loginPassword').value = 'test';

    const formData = new FormData();
    formData.append('username', 'test');
    formData.append('password', 'test');

    try {
        const response = await fetch(`${API_URL}/auth/login`, {
            method: 'POST',
            body: formData
        });

        if (response.ok) {
            const data = await response.json();
            authToken = data.access_token;
            localStorage.setItem('authToken', authToken);
            await checkAuth();
            showNotification('Тестовый вход выполнен', 'success');
        } else {
            const error = await response.json();
            showError(error.detail || 'Ошибка тестового входа');
        }
    } catch (error) {
        console.error('Quick login error:', error);
        showError('Ошибка соединения с сервером');
    }
}

// Обработка регистрации
async function handleRegister(event) {
    event.preventDefault();

    const userData = {
        username: document.getElementById('regUsername').value,
        password: document.getElementById('regPassword').value,
        fio: document.getElementById('regFio').value,
        tab_no: document.getElementById('regTabNo').value,
        email: document.getElementById('regEmail').value
    };

    try {
        const response = await fetch(`${API_URL}/auth/register`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(userData)
        });

        if (response.ok) {
            const data = await response.json();
            authToken = data.access_token;
            localStorage.setItem('authToken', authToken);
            await checkAuth();
            showNotification('Регистрация успешна', 'success');
        } else {
            const error = await response.json();
            showError(error.detail || 'Ошибка регистрации');
        }
    } catch (error) {
        console.error('Register error:', error);
        showError('Ошибка соединения с сервером');
    }
}

// Выход
function logout() {
    authToken = null;
    currentUser = null;
    localStorage.removeItem('authToken');
    showAuth();
    showNotification('Вы вышли из системы', 'info');
}

// Показать форму входа
function showAuth() {
    document.getElementById('authSection').style.display = 'flex';
    document.getElementById('mainSection').style.display = 'none';
    document.getElementById('navUser').style.display = 'none';
}

// Показать основной интерфейс
function showMain() {
    document.getElementById('authSection').style.display = 'none';
    document.getElementById('mainSection').style.display = 'block';
    document.getElementById('navUser').style.display = 'flex';
    document.getElementById('userInfo').textContent = currentUser.fio || currentUser.username;
}

// Показать ошибку
function showError(message) {
    const errorDiv = document.getElementById('authError');
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
    setTimeout(() => {
        errorDiv.style.display = 'none';
    }, 5000);
}

// Показать уведомление
function showNotification(message, type = 'info') {
    const notification = document.getElementById('notification');
    notification.textContent = message;
    notification.className = `notification ${type}`;
    notification.style.display = 'block';

    setTimeout(() => {
        notification.style.display = 'none';
    }, 3000);
}

// Загрузка списка командировок
async function loadTrips() {
    try {
        const response = await fetch(`${API_URL}/trips/`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            const trips = await response.json();
            // Сортировка: последние командировки сверху
            trips.sort((a, b) => {
                const dateA = a.created_at ? new Date(a.created_at).getTime() : 0;
                const dateB = b.created_at ? new Date(b.created_at).getTime() : 0;
                if (dateA !== dateB) {
                    return dateB - dateA;
                }
                return (b.id || 0) - (a.id || 0);
            });
            allTrips = trips;
            applyTripFilters();
        } else {
            showNotification('Ошибка загрузки командировок', 'error');
        }
    } catch (error) {
        console.error('Load trips error:', error);
        showNotification('Ошибка соединения', 'error');
    }
}

// Отображение списка командировок
function displayTrips(trips) {
    const tripsList = document.getElementById('tripsList');

    if (trips.length === 0) {
        tripsList.innerHTML = `
            <div style="text-align: center; padding: 40px; background: white; border-radius: 12px;">
                <h3 style="color: #888; margin-bottom: 10px;">Нет командировок</h3>
                <p style="color: #aaa;">Создайте первую командировку, нажав кнопку выше</p>
            </div>
        `;
        return;
    }

    tripsList.innerHTML = trips.map(trip => `
        <div class="trip-card" onclick="viewTrip(${trip.id})">
            <div class="trip-header">
                <div class="trip-title">
                    📍 ${trip.destination_city}
                </div>
                <div class="trip-status status-draft">
                    ID: ${trip.id}
                </div>
            </div>
            <div class="trip-details">
                <div class="trip-detail-item">
                    📅 ${formatDate(trip.date_from)} - ${formatDate(trip.date_to)}
                </div>
                <div class="trip-detail-item">
                    🏢 ${trip.destination_org || 'Не указано'}
                </div>
                <div class="trip-detail-item">
                    🎯 ${trip.purpose ? trip.purpose.substring(0, 50) + '...' : 'Без описания'}
                </div>
            </div>
            <div class="trip-actions" style="margin-top: 12px; display: flex; gap: 8px;">
                <button onclick="showEditTripModal(${trip.id}, event)" class="btn btn-secondary btn-small">
                    ✏️ Редактировать
                </button>
                <button onclick="deleteTrip(${trip.id}, event)" class="btn btn-danger btn-small">
                    🗑️ Удалить
                </button>
            </div>
        </div>
    `).join('');
}

function applyTripFilters() {
    const filterCity = document.getElementById('filterCity');
    const filterOrg = document.getElementById('filterOrg');
    const filterDateFrom = document.getElementById('filterDateFrom');
    const filterDateTo = document.getElementById('filterDateTo');

    const cityValue = (filterCity?.value || '').trim().toLowerCase();
    const orgValue = (filterOrg?.value || '').trim().toLowerCase();
    const dateFromValue = filterDateFrom?.value || '';
    const dateToValue = filterDateTo?.value || '';

    const dateFrom = dateFromValue ? new Date(dateFromValue) : null;
    const dateTo = dateToValue ? new Date(dateToValue) : null;
    if (dateTo) {
        dateTo.setHours(23, 59, 59, 999);
    }

    const filtered = allTrips.filter((trip) => {
        const city = (trip.destination_city || '').toLowerCase();
        const org = (trip.destination_org || '').toLowerCase();

        if (cityValue && !city.includes(cityValue)) return false;
        if (orgValue && !org.includes(orgValue)) return false;

        const tripStart = trip.date_from ? new Date(trip.date_from) : null;
        const tripEnd = trip.date_to ? new Date(trip.date_to) : null;

        if (dateFrom && tripEnd && tripEnd < dateFrom) return false;
        if (dateTo && tripStart && tripStart > dateTo) return false;

        return true;
    });

    displayTrips(filtered);
}

function resetTripFilters() {
    const filterCity = document.getElementById('filterCity');
    const filterOrg = document.getElementById('filterOrg');
    const filterDateFrom = document.getElementById('filterDateFrom');
    const filterDateTo = document.getElementById('filterDateTo');

    if (filterCity) filterCity.value = '';
    if (filterOrg) filterOrg.value = '';
    if (filterDateFrom) filterDateFrom.value = '';
    if (filterDateTo) filterDateTo.value = '';

    applyTripFilters();
}

// Форматирование даты
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('ru-RU');
}

// Показать модальное окно создания командировки
function showCreateTripModal() {
    const createModal = document.getElementById('createTripModal');
    const editModal = document.getElementById('editTripModal');
    const editReceiptModal = document.getElementById('editReceiptModal');
    const previewModal = document.getElementById('previewModal');
    const progressModal = document.getElementById('progressModal');
    const viewModal = document.getElementById('viewTripModal');

    if (editModal) editModal.style.display = 'none';
    if (editReceiptModal) editReceiptModal.style.display = 'none';
    if (previewModal) previewModal.style.display = 'none';
    if (progressModal) progressModal.style.display = 'none';
    if (viewModal) viewModal.style.display = 'none';

    createModal.style.display = 'block';
}

// Закрыть модальное окно создания
function closeCreateTripModal() {
    document.getElementById('createTripModal').style.display = 'none';
    document.getElementById('createTripForm').reset();
}

// Создание командировки
async function handleCreateTrip(event) {
    event.preventDefault();

    // Валидация дат
    const dateFromStr = document.getElementById('tripDateFrom').value;
    const dateToStr = document.getElementById('tripDateTo').value;

    if (!dateFromStr || !dateToStr) {
        showNotification('Укажите даты командировки!', 'error');
        return;
    }

    const dateFrom = new Date(dateFromStr);
    const dateTo = new Date(dateToStr);

    if (dateTo < dateFrom) {
        showNotification('Ошибка: Дата возвращения должна быть позже даты отправления!', 'error');
        logger.warn('Validation failed: date_to < date_from', { dateFrom: dateFromStr, dateTo: dateToStr });
        return;
    }

    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const maxDate = new Date(today.getFullYear() + 2, today.getMonth(), today.getDate());

    if (dateFrom > maxDate) {
        showNotification('Ошибка: Дата командировки не может быть больше чем через 2 года!', 'error');
        logger.warn('Validation failed: date too far in future', { dateFrom: dateFromStr });
        return;
    }

    const tripData = {
        destination_city: document.getElementById('tripCity').value,
        destination_org: document.getElementById('tripOrg').value,
        date_from: dateFromStr,
        date_to: dateToStr,
        departure_time: document.getElementById('tripDepartureTime').value,
        arrival_time: document.getElementById('tripArrivalTime').value,
        purpose: document.getElementById('tripPurpose').value,
        advance_rub: parseFloat(document.getElementById('tripAdvance').value) || 0,
        per_diem_rate: parseFloat(document.getElementById('tripPerDiem').value) || 2000,
        meals_breakfast_count: parseInt(document.getElementById('tripBreakfast').value) || 0,
        meals_lunch_count: parseInt(document.getElementById('tripLunch').value) || 0,
        meals_dinner_count: parseInt(document.getElementById('tripDinner').value) || 0
    };

    try {
        const response = await fetch(`${API_URL}/trips/`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(tripData)
        });

        if (response.ok) {
            const trip = await response.json();
            closeCreateTripModal();
            showNotification('Командировка создана', 'success');
            loadTrips();
            // Автоматически открыть окно командировки для загрузки документов
            viewTrip(trip.id);
        } else {
            const error = await response.json();
            showNotification(error.detail || 'Ошибка создания', 'error');
        }
    } catch (error) {
        console.error('Create trip error:', error);
        showNotification('Ошибка соединения', 'error');
    }
}

// Просмотр командировки
async function viewTrip(tripId) {
    currentTripId = tripId;

    try {
        const response = await fetch(`${API_URL}/trips/${tripId}`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            const trip = await response.json();
            displayTripDetails(trip);
            document.getElementById('viewTripModal').style.display = 'block';
        } else {
            showNotification('Ошибка загрузки командировки', 'error');
        }
    } catch (error) {
        console.error('View trip error:', error);
        showNotification('Ошибка соединения', 'error');
    }
}

// Отображение деталей командировки
function displayTripDetails(trip) {
    document.getElementById('viewTripId').textContent = trip.id;

    const detailsHtml = `
        <div style="display: flex; justify-content: flex-end; margin-bottom: 15px;">
            <button onclick="closeViewTripModal(); showEditTripModal(${trip.id})" class="btn btn-secondary">
                ✏️ Редактировать командировку
            </button>
        </div>
        <div class="detail-row">
            <div class="detail-label">Город:</div>
            <div class="detail-value">${trip.destination_city}</div>
        </div>
        <div class="detail-row">
            <div class="detail-label">Организация:</div>
            <div class="detail-value">${trip.destination_org || 'Не указано'}</div>
        </div>
        <div class="detail-row">
            <div class="detail-label">Период:</div>
            <div class="detail-value">${formatDate(trip.date_from)} - ${formatDate(trip.date_to)}</div>
        </div>
        <div class="detail-row">
            <div class="detail-label">Время отправления:</div>
            <div class="detail-value">${trip.departure_time || 'Не указано'}</div>
        </div>
        <div class="detail-row">
            <div class="detail-label">Время прибытия:</div>
            <div class="detail-value">${trip.arrival_time || 'Не указано'}</div>
        </div>
        <div class="detail-row">
            <div class="detail-label">Цель:</div>
            <div class="detail-value">${trip.purpose}</div>
        </div>
        <div class="detail-row">
            <div class="detail-label">Аванс:</div>
            <div class="detail-value">${trip.advance_rub} руб</div>
        </div>
        <div class="detail-row">
            <div class="detail-label">Питание:</div>
            <div class="detail-value">Завтраки: ${trip.meals_breakfast_count}, Обеды: ${trip.meals_lunch_count}, Ужины: ${trip.meals_dinner_count}</div>
        </div>
    `;

    document.getElementById('tripDetails').innerHTML = detailsHtml;

    // Загрузить чеки
    loadReceipts(trip.id);
}

// Закрыть модальное окно просмотра
function closeViewTripModal() {
    document.getElementById('viewTripModal').style.display = 'none';
    currentTripId = null;
}

// Загрузка чеков
async function loadReceipts(tripId) {
    try {
        const response = await fetch(`${API_URL}/trips/${tripId}`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            const trip = await response.json();
            displayReceipts(trip.receipts || []);
        }
    } catch (error) {
        console.error('Load receipts error:', error);
    }
}

// Отображение чеков
function displayReceipts(receipts) {
    const receiptsList = document.getElementById('receiptsList');

    if (receipts.length === 0) {
        receiptsList.innerHTML = '<p style="color: #888;">Нет загруженных чеков</p>';
        return;
    }

    // Сортировка: последние загрузки сверху
    const orderedReceipts = [...receipts].sort((a, b) => (b.id || 0) - (a.id || 0));

    receiptsList.innerHTML = orderedReceipts.map(receipt => {
        const dateValue = receipt.receipt_date ? new Date(receipt.receipt_date).toISOString().slice(0, 10) : '';
        const amountValue = receipt.amount != null ? receipt.amount : '';
        const orgValue = receipt.org_name || '';
        const displayCategory = getCategoryName(receipt.category);
        const categoryValue = receipt.category || 'other';
        return `
        <div class="receipt-item">
            <div class="receipt-info">
                <span class="receipt-category">${displayCategory}</span>
                <span>${receipt.receipt_date ? formatDate(receipt.receipt_date) : 'Без даты'}</span>
                ${receipt.has_qr ? ' ✓ QR' : ''}
            </div>
            <div class="receipt-amount">${receipt.amount || 0} ₽</div>
            <div class="receipt-edit-inline">
                <input type="text" class="receipt-input receipt-category-input" value="${displayCategory}" data-receipt-id="${receipt.id}" data-field="category" placeholder="Категория">
                <input type="number" class="receipt-input receipt-amount-input" value="${amountValue}" data-receipt-id="${receipt.id}" data-field="amount" step="0.01" placeholder="Сумма">
                <input type="date" class="receipt-input receipt-date-input" value="${dateValue}" data-receipt-id="${receipt.id}" data-field="receipt_date">
            </div>
            <div class="receipt-actions">
                <button onclick="saveReceiptInline(${receipt.id})" class="btn btn-secondary btn-small">Сохранить</button>
                <button onclick="deleteReceipt(${receipt.id})" class="btn btn-danger btn-small">Удалить</button>
            </div>
        </div>
        `;
    }).join('');
}

// Получить название категории
function getCategoryName(category) {
    const categories = {
        'taxi': 'Такси',
        'fuel': 'Топливо',
        'airplane': 'Самолет',
        'train': 'Поезд',
        'bus': 'Автобус',
        'hotel': 'Гостиница',
        'restaurant': 'Автобус',
        'other': 'Представительские'
    };
    return categories[category] || category;
}

function isKnownCategory(category) {
    return ['taxi', 'fuel', 'airplane', 'train', 'bus', 'hotel', 'restaurant', 'other'].includes(category);
}

function toggleCustomCategory(selectEl, groupEl) {
    if (!selectEl || !groupEl) return;
    groupEl.style.display = selectEl.value === 'custom' ? 'block' : 'none';
}

// Загрузка чеков (поддержка множественной загрузки)
async function handleReceiptUpload(event) {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    // Сохраняем tripId в начале, чтобы не потерять его
    const tripId = currentTripId;
    if (!tripId) {
        showNotification('Ошибка: не выбрана командировка', 'error');
        return;
    }

    const categorySelect = document.getElementById('receiptCategory');
    const categoryCustomInput = document.getElementById('receiptCategoryCustom');
    let category = categorySelect ? categorySelect.value : 'other';
    if (category === 'custom') {
        const customValue = (categoryCustomInput ? categoryCustomInput.value : '').trim();
        if (!customValue) {
            showNotification('Укажите свой тип документа', 'error');
            return;
        }
        category = customValue;
    }

    // Загружаем все файлы по очереди
    let successCount = 0;
    let failCount = 0;

    // Показываем модальное окно прогресса
    showProgressModal(files.length);

    for (let i = 0; i < files.length; i++) {
        const file = files[i];

        // Обновляем прогресс
        updateProgress(i + 1, files.length, `Обработка: ${file.name}`);

        const formData = new FormData();
        formData.append('file', file);
        formData.append('category', category);

        try {
            const response = await fetch(`${API_URL}/receipts/trip/${tripId}/upload`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${authToken}`
                },
                body: formData
            });

            if (response.ok) {
                successCount++;
                const result = await response.json();
                console.log(`[${i+1}/${files.length}] Загружен: ${file.name}`);
                if (result && Array.isArray(result.warnings) && result.warnings.length > 0) {
                    if (result.warnings.includes('amount_out_of_range')) {
                        showNotification(`Проверьте сумму в ${file.name} (вне диапазона)`, 'error');
                    } else if (result.warnings.includes('amount_invalid')) {
                        showNotification(`Проверьте сумму в ${file.name} (некорректная)`, 'error');
                    } else if (result.warnings.includes('amount_missing')) {
                        showNotification(`Сумма не распознана: ${file.name}. Введите вручную.`, 'error');
                    }
                }

                // Обновляем список чеков сразу после каждой успешной загрузки
                await loadReceipts(tripId);
            } else {
                failCount++;
                let errorDetail = 'Ошибка загрузки';
                try {
                    const error = await response.json();
                    errorDetail = error.detail || errorDetail;
                } catch (_) {
                    // ignore
                }
                if (response.status === 409) {
                    showNotification(`Дубликат: ${file.name}`, 'error');
                } else {
                    showNotification(`${file.name}: ${errorDetail}`, 'error');
                }
                console.error(`[${i+1}/${files.length}] Ошибка ${file.name}:`, errorDetail);
            }
        } catch (error) {
            failCount++;
            console.error(`[${i+1}/${files.length}] Ошибка соединения для ${file.name}:`, error);
        }
    }

   
    // Закрываем модальное окно прогресса
    hideProgressModal(); // Показываем итоговый результат
    if (failCount === 0) {
        showNotification(`Все ${successCount} чеков загружены успешно!`, 'success');
    } else if (successCount === 0) {
        showNotification(`Не удалось загрузить ни один чек (${failCount} ошибок)`, 'error');
    } else {
        showNotification(`Загружено: ${successCount}, Ошибок: ${failCount}`, 'info');
    }

    loadReceipts(tripId);
    event.target.value = ''; // Очистить input
}

// Редактирование чека
async function editReceipt(receiptId) {
    try {
        if (!currentTripId) {
            showNotification('Ошибка: не выбрана командировка', 'error');
            return;
        }
        // Получаем данные чека
        const response = await fetch(`${API_URL}/trips/${currentTripId}`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (!response.ok) {
            showNotification('Ошибка загрузки чека', 'error');
            return;
        }

        const trip = await response.json();
        const receipts = Array.isArray(trip.receipts) ? trip.receipts : [];
        const receipt = receipts.find(r => String(r.id) === String(receiptId));

        if (receipt) {
            const viewModal = document.getElementById('viewTripModal');
            if (viewModal) viewModal.style.display = 'none';

            // Заполняем форму
            document.getElementById('editReceiptId').value = receipt.id;
            const categorySelect = document.getElementById('editReceiptCategory');
            const categoryCustomInput = document.getElementById('editReceiptCategoryCustom');
            const categoryCustomGroup = document.getElementById('editReceiptCategoryCustomGroup');

            if (receipt.category && isKnownCategory(receipt.category)) {
                categorySelect.value = receipt.category;
                if (categoryCustomInput) categoryCustomInput.value = '';
            } else if (receipt.category) {
                categorySelect.value = 'custom';
                if (categoryCustomInput) categoryCustomInput.value = receipt.category;
            } else {
                categorySelect.value = 'other';
                if (categoryCustomInput) categoryCustomInput.value = '';
            }

            toggleCustomCategory(categorySelect, categoryCustomGroup);
            document.getElementById('editReceiptAmount').value = receipt.amount || '';

            // Форматируем дату для datetime-local input
            if (receipt.receipt_date) {
                const date = new Date(receipt.receipt_date);
                const dateStr = date.toISOString().slice(0, 16); // YYYY-MM-DDTHH:mm
                document.getElementById('editReceiptDate').value = dateStr;
            } else {
                document.getElementById('editReceiptDate').value = '';
            }

                // Показываем модальное окно
                document.getElementById('editReceiptModal').style.display = 'block';
            } else {
                showNotification('Чек не найден', 'error');
            }
    } catch (error) {
        console.error('Load receipt for edit error:', error);
        showNotification('Ошибка загрузки чека', 'error');
    }
}

// Закрыть модальное окно редактирования чека
function closeEditReceiptModal() {
    document.getElementById('editReceiptModal').style.display = 'none';
    document.getElementById('editReceiptForm').reset();
    const categorySelect = document.getElementById('editReceiptCategory');
    const categoryCustomGroup = document.getElementById('editReceiptCategoryCustomGroup');
    toggleCustomCategory(categorySelect, categoryCustomGroup);
}

// Обработка редактирования чека
async function handleEditReceipt(event) {
    event.preventDefault();

    const receiptId = document.getElementById('editReceiptId').value;
    const categorySelect = document.getElementById('editReceiptCategory');
    const categoryCustomInput = document.getElementById('editReceiptCategoryCustom');
    let category = categorySelect.value;
    if (category === 'custom') {
        const customValue = (categoryCustomInput ? categoryCustomInput.value : '').trim();
        if (!customValue) {
            showNotification('Укажите свой тип документа', 'error');
            return;
        }
        category = customValue;
    }
    const receiptData = {
        category: category,
        amount: parseFloat(document.getElementById('editReceiptAmount').value),
        receipt_date: document.getElementById('editReceiptDate').value || null
    };

    try {
        const response = await fetch(`${API_URL}/receipts/${receiptId}`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(receiptData)
        });

        if (response.ok) {
            closeEditReceiptModal();
            showNotification('Чек обновлен!', 'success');
            await loadReceipts(currentTripId);
        } else {
            const error = await response.json();
            showNotification(error.detail || 'Ошибка обновления', 'error');
        }
    } catch (error) {
        console.error('Update receipt error:', error);
        showNotification('Ошибка соединения', 'error');
    }
}

// Удаление чека
async function deleteReceipt(receiptId) {
    if (!confirm('Удалить чек?')) return;

    try {
        const response = await fetch(`${API_URL}/receipts/${receiptId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            showNotification('Чек удален', 'success');
            loadReceipts(currentTripId);
        } else {
            showNotification('Ошибка удаления', 'error');
        }
    } catch (error) {
        console.error('Delete receipt error:', error);
        showNotification('Ошибка соединения', 'error');
    }
}

// Генерация документов
async function generateDocuments() {
    logger.info('Начало генерации документов', { tripId: currentTripId });

    try {
        showNotification('Генерация документов...', 'info');

        logger.debug('Отправка запроса на генерацию', {
            url: `${API_URL}/trips/${currentTripId}/generate`
        });

        const response = await fetch(`${API_URL}/trips/${currentTripId}/generate`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        logger.debug('Получен ответ от сервера', {
            status: response.status,
            statusText: response.statusText
        });

        if (response.ok) {
            const result = await response.json();
            logger.info('Документы успешно сгенерированы', { result });

            showNotification('Документы успешно сгенерированы', 'success');
            document.getElementById('downloadBtn').style.display = 'inline-block';

            const statusDiv = document.getElementById('documentsStatus');
            statusDiv.innerHTML = `
                <h4 style="color: #66BB6A; margin-bottom: 10px;">✓ Документы готовы</h4>
                <p>Приказ, Суточные, Авансовый отчет, Служебная записка</p>
                <p style="margin-top: 10px;">Архив готов к скачиванию</p>
            `;
        } else {
            const error = await response.json();
            logger.error('Ошибка генерации документов', {
                status: response.status,
                error: error
            });

            showNotification(error.detail || 'Ошибка генерации', 'error');

            const statusDiv = document.getElementById('documentsStatus');
            statusDiv.innerHTML = `
                <h4 style="color: #dc3545;">✗ Ошибка генерации</h4>
                <p>${error.detail}</p>
            `;
        }
    } catch (error) {
        logger.error('Критическая ошибка при генерации', {
            error: error.message,
            stack: error.stack
        });

        showNotification('Ошибка соединения', 'error');
    }
}

// Скачивание архива
async function downloadPackage() {
    try {
        const response = await fetch(`${API_URL}/trips/${currentTripId}/download`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `trip_${currentTripId}_package.zip`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            showNotification('Архив скачан', 'success');
        } else {
            showNotification('Ошибка скачивания', 'error');
        }
    } catch (error) {
        console.error('Download error:', error);
        showNotification('Ошибка соединения', 'error');
    }
}

// Показать модальное окно редактирования
function showEditTripModal(tripId, event) {
    if (event) {
        event.stopPropagation(); // Предотвратить открытие viewTrip
    }

    // Загрузить данные командировки
    fetch(`${API_URL}/trips/${tripId}`, {
        headers: {
            'Authorization': `Bearer ${authToken}`
        }
    })
    .then(response => response.json())
    .then(trip => {
        const createModal = document.getElementById('createTripModal');
        const viewModal = document.getElementById('viewTripModal');
        if (createModal) createModal.style.display = 'none';
        if (viewModal) viewModal.style.display = 'none';

        // Заполнить форму
        document.getElementById('editTripId').value = trip.id;
        document.getElementById('editTripCity').value = trip.destination_city;
        document.getElementById('editTripOrg').value = trip.destination_org || '';
        document.getElementById('editTripDateFrom').value = trip.date_from;
        document.getElementById('editTripDateTo').value = trip.date_to;
        document.getElementById('editTripDepartureTime').value = trip.departure_time || '';
        document.getElementById('editTripArrivalTime').value = trip.arrival_time || '';
        document.getElementById('editTripPurpose').value = trip.purpose;
        document.getElementById('editTripAdvance').value = trip.advance_rub;
        document.getElementById('editTripBreakfast').value = trip.meals_breakfast_count;
        document.getElementById('editTripLunch').value = trip.meals_lunch_count;
        document.getElementById('editTripDinner').value = trip.meals_dinner_count;

        // Показать модальное окно
        document.getElementById('editTripModal').style.display = 'block';
    })
    .catch(error => {
        console.error('Load trip for edit error:', error);
        showNotification('Ошибка загрузки данных', 'error');
    });
}

// Закрыть модальное окно редактирования
function closeEditTripModal() {
    document.getElementById('editTripModal').style.display = 'none';
    document.getElementById('editTripForm').reset();
}

// Обновление командировки
async function handleEditTrip(event) {
    event.preventDefault();

    const tripId = document.getElementById('editTripId').value;

    // Валидация дат при редактировании
    const dateFromStr = document.getElementById('editTripDateFrom').value;
    const dateToStr = document.getElementById('editTripDateTo').value;

    if (!dateFromStr || !dateToStr) {
        showNotification('Укажите даты командировки!', 'error');
        return;
    }

    const dateFrom = new Date(dateFromStr);
    const dateTo = new Date(dateToStr);

    if (dateTo < dateFrom) {
        showNotification('Ошибка: Дата возвращения должна быть позже даты отправления!', 'error');
        logger.warn('Edit validation failed: date_to < date_from', { dateFrom: dateFromStr, dateTo: dateToStr });
        return;
    }

    const tripData = {
        destination_city: document.getElementById('editTripCity').value,
        destination_org: document.getElementById('editTripOrg').value,
        date_from: dateFromStr,
        date_to: dateToStr,
        departure_time: document.getElementById('editTripDepartureTime').value || null,
        arrival_time: document.getElementById('editTripArrivalTime').value || null,
        purpose: document.getElementById('editTripPurpose').value,
        advance_rub: parseFloat(document.getElementById('editTripAdvance').value) || 0,
        meals_breakfast_count: parseInt(document.getElementById('editTripBreakfast').value) || 0,
        meals_lunch_count: parseInt(document.getElementById('editTripLunch').value) || 0,
        meals_dinner_count: parseInt(document.getElementById('editTripDinner').value) || 0
    };

    try {
        const response = await fetch(`${API_URL}/trips/${tripId}`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(tripData)
        });

        if (response.ok) {
            closeEditTripModal();
            showNotification('Командировка обновлена! Пересгенерируйте документы.', 'success');
            loadTrips();

            // Если открыто окно просмотра, обновить его
            if (currentTripId == tripId) {
                viewTrip(tripId);
            }
        } else {
            const error = await response.json();
            showNotification(error.detail || 'Ошибка обновления', 'error');
        }
    } catch (error) {
        console.error('Update trip error:', error);
        showNotification('Ошибка соединения', 'error');
    }
}

// Удаление командировки
async function deleteTrip(tripId, event) {
    if (event) {
        event.stopPropagation(); // Предотвратить открытие viewTrip
    }

    logger.info('Попытка удаления командировки', { tripId });

    if (!confirm('Вы уверены, что хотите удалить эту командировку?\n\nВсе чеки и документы будут удалены без возможности восстановления.')) {
        logger.debug('Удаление отменено пользователем', { tripId });
        return;
    }

    try {
        logger.debug('Отправка запроса на удаление', { tripId });

        const response = await fetch(`${API_URL}/trips/${tripId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            logger.info('Командировка успешно удалена', { tripId });
            showNotification('Командировка успешно удалена', 'success');
            await loadTrips();
        } else {
            const error = await response.json();
            logger.error('Ошибка удаления командировки', {
                tripId,
                status: response.status,
                error: error
            });
            showNotification(error.detail || 'Ошибка удаления', 'error');
        }
    } catch (error) {
        logger.error('Критическая ошибка при удалении', {
            tripId,
            error: error.message
        });
        showNotification('Ошибка соединения с сервером', 'error');
    }
}

// ========== ПРОГРЕСС-ИНДИКАТОР ==========

function showProgressModal(totalFiles) {
    const modal = document.getElementById('progressModal');
    const progressBar = document.getElementById('progressBar');
    const progressText = document.getElementById('progressText');
    const progressDetails = document.getElementById('progressDetails');

    progressBar.style.width = '0%';
    progressText.textContent = 'Начинаем обработку...';
    progressDetails.textContent = `0 из ${totalFiles} файлов`;

    modal.style.display = 'block';
}

function updateProgress(current, total, message) {
    const progressBar = document.getElementById('progressBar');
    const progressText = document.getElementById('progressText');
    const progressDetails = document.getElementById('progressDetails');

    const percentage = Math.round((current / total) * 100);

    progressBar.style.width = percentage + '%';
    progressText.textContent = message;
    progressDetails.textContent = `${current} из ${total} файлов`;
}

function hideProgressModal() {
    setTimeout(() => {
        document.getElementById('progressModal').style.display = 'none';
    }, 500);
}

// ========== ПРЕДПРОСМОТР ДАННЫХ ==========

async function showPreview() {
    if (!currentTripId) {
        showNotification('Ошибка: не выбрана командировка', 'error');
        return;
    }

    try {
        const response = await fetch(`${API_URL}/trips/${currentTripId}/preview`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            const data = await response.json();
            displayPreview(data);
        } else {
            const error = await response.json();
            showNotification(error.detail || 'Ошибка получения данных', 'error');
        }
    } catch (error) {
        console.error('Preview error:', error);
        showNotification('Ошибка соединения', 'error');
    }
}

function displayPreview(data) {
    const previewContent = document.getElementById('previewContent');
    const previewWarnings = document.getElementById('previewWarnings');
    const confirmBtn = document.getElementById('confirmGenerateBtn');

    // Форматирование расходов по категориям
    const expensesHtml = Object.entries(data.expenses_by_category).map(([category, amount]) => {
        return `<tr>
            <td>${getCategoryName(category)}</td>
            <td style="text-align: right; font-weight: bold;">${amount.toFixed(2)} ₽</td>
        </tr>`;
    }).join('');

    // Основной контент
    previewContent.innerHTML = `
        <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
            <h3 style="margin-top: 0;">📍 ${data.destination}</h3>
            <p><strong>Даты:</strong> ${data.dates}</p>
            <p><strong>Чеков загружено:</strong> ${data.receipts_count} шт.</p>
        </div>

        <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
            <thead>
                <tr style="background: #e9ecef;">
                    <th style="padding: 10px; text-align: left; border: 1px solid #dee2e6;">Категория</th>
                    <th style="padding: 10px; text-align: right; border: 1px solid #dee2e6;">Сумма</th>
                </tr>
            </thead>
            <tbody>
                ${expensesHtml || '<tr><td colspan="2" style="text-align: center; padding: 10px; color: #888;">Нет расходов по чекам</td></tr>'}
                <tr style="background: #fff3cd;">
                    <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>Суточные</strong><br>
                        <small>(${data.per_diem_days.toFixed(2)} дней × ${data.per_diem_total / data.per_diem_days || 0} ₽ - вычет ${data.per_diem_deduction.toFixed(2)} ₽)</small>
                    </td>
                    <td style="padding: 10px; text-align: right; border: 1px solid #dee2e6; font-weight: bold;">${data.per_diem_to_pay.toFixed(2)} ₽</td>
                </tr>
            </tbody>
            <tfoot>
                <tr style="background: #d4edda; font-weight: bold; font-size: 18px;">
                    <td style="padding: 15px; border: 1px solid #dee2e6;">ИТОГО к расходу</td>
                    <td style="padding: 15px; text-align: right; border: 1px solid #dee2e6;">${data.total_expenses.toFixed(2)} ₽</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #dee2e6;">Аванс выдан</td>
                    <td style="padding: 10px; text-align: right; border: 1px solid #dee2e6;">${data.advance_rub.toFixed(2)} ₽</td>
                </tr>
                <tr style="background: ${data.to_return > 0 ? '#f8d7da' : '#d1ecf1'}; font-weight: bold;">
                    <td style="padding: 10px; border: 1px solid #dee2e6;">${data.to_return > 0 ? 'К возврату' : 'К доплате'}</td>
                    <td style="padding: 10px; text-align: right; border: 1px solid #dee2e6;">${Math.abs(data.to_return).toFixed(2)} ₽</td>
                </tr>
            </tfoot>
        </table>
    `;

    // Предупреждения и ошибки
    let warningsHtml = '';

    if (data.errors && data.errors.length > 0) {
        warningsHtml += `<div style="background: #f8d7da; border: 1px solid #f5c6cb; padding: 15px; border-radius: 5px; margin-bottom: 10px;">
            <h4 style="color: #721c24; margin-top: 0;">❌ Ошибки:</h4>
            <ul style="margin: 0; padding-left: 20px;">
                ${data.errors.map(err => `<li style="color: #721c24;">${err}</li>`).join('')}
            </ul>
        </div>`;
    }

    if (data.warnings && data.warnings.length > 0) {
        warningsHtml += `<div style="background: #fff3cd; border: 1px solid #ffeeba; padding: 15px; border-radius: 5px;">
            <h4 style="color: #856404; margin-top: 0;">⚠️ Предупреждения:</h4>
            <ul style="margin: 0; padding-left: 20px;">
                ${data.warnings.map(warn => `<li style="color: #856404;">${warn}</li>`).join('')}
            </ul>
        </div>`;
    }

    previewWarnings.innerHTML = warningsHtml;

    // Активность кнопки генерации
    if (data.can_generate) {
        confirmBtn.disabled = false;
        confirmBtn.style.opacity = '1';
    } else {
        confirmBtn.disabled = true;
        confirmBtn.style.opacity = '0.5';
    }

    // Показываем модальное окно
    document.getElementById('previewModal').style.display = 'block';
}

function closePreviewModal() {
    document.getElementById('previewModal').style.display = 'none';
}

async function confirmGeneration() {
    closePreviewModal();
    await generateDocuments();
}

// ========== ЗАКРЫТИЕ МОДАЛЬНЫХ ОКОН ==========

// Закрытие модальных окон по клику вне их
window.onclick = function(event) {
    // Окна закрываются только по кнопке "крестик"
}

// Сохранение чека из встроенных полей редактирования
async function saveReceiptInline(receiptId) {
    const categoryInput = document.querySelector(`.receipt-category-input[data-receipt-id="${receiptId}"]`);
    const amountInput = document.querySelector(`.receipt-amount-input[data-receipt-id="${receiptId}"]`);
    const dateInput = document.querySelector(`.receipt-date-input[data-receipt-id="${receiptId}"]`);

    if (!categoryInput || !amountInput || !dateInput) {
        showNotification('Ошибка: не найдены поля редактирования', 'error');
        return;
    }

    const categoryRaw = categoryInput.value.trim();
    const amountRaw = amountInput.value;
    const dateRaw = dateInput.value;

    if (!categoryRaw) {
        showNotification('Укажите категорию', 'error');
        return;
    }

    const amountValue = amountRaw !== '' ? parseFloat(amountRaw) : null;
    if (amountRaw !== '' && Number.isNaN(amountValue)) {
        showNotification('Некорректная сумма', 'error');
        return;
    }

    let category = categoryRaw;
    const categoryLower = categoryRaw.toLowerCase();
    if (categoryLower === 'самолет') category = 'airplane';
    if (categoryLower === 'поезд') category = 'train';
    if (categoryLower === 'автобус') category = 'bus';
    if (categoryLower === 'представительские') category = 'other';
    if (categoryLower === 'такси') category = 'taxi';
    if (categoryLower === 'топливо') category = 'fuel';
    if (categoryLower === 'гостиница') category = 'hotel';
    if (categoryLower === 'ресторан') category = 'bus';
    if (categoryLower === 'restaurant') category = 'bus';
    if (categoryLower === 'bus') category = 'bus';

    const receiptData = {
        category: category,
        amount: amountValue,
        receipt_date: dateRaw || null
    };

    try {
        const response = await fetch(`${API_URL}/receipts/${receiptId}`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(receiptData)
        });

        if (response.ok) {
            showNotification('Чек обновлен!', 'success');
            await loadReceipts(currentTripId);
        } else {
            const error = await response.json();
            showNotification(error.detail || 'Ошибка обновления', 'error');
        }
    } catch (error) {
        console.error('Update receipt error:', error);
        showNotification('Ошибка соединения', 'error');
    }
}

// ========== УМНЫЙ ВЫБОР ДАТ ==========

/**
 * Инициализирует умный выбор дат для форм создания и редактирования
 * После выбора даты отправления автоматически открывается дата возвращения
 */
function initSmartDatePickers() {
    logger.info('Инициализация умного выбора дат');

    // Для формы создания командировки
    const createDateFrom = document.getElementById('tripDateFrom');
    const createDateTo = document.getElementById('tripDateTo');

    if (createDateFrom && createDateTo) {
        setupSmartDatePair(createDateFrom, createDateTo, 'create');
    }

    // Для формы редактирования командировки
    const editDateFrom = document.getElementById('editTripDateFrom');
    const editDateTo = document.getElementById('editTripDateTo');

    if (editDateFrom && editDateTo) {
        setupSmartDatePair(editDateFrom, editDateTo, 'edit');
    }
}

/**
 * Настраивает пару дат (от-до) с умным поведением
 * @param {HTMLInputElement} dateFromInput - Поле даты отправления
 * @param {HTMLInputElement} dateToInput - Поле даты возвращения
 * @param {string} formType - Тип формы ('create' или 'edit')
 */
function setupSmartDatePair(dateFromInput, dateToInput, formType) {
    // Разрешаем выбирать прошлые даты (ничего не ограничиваем по min)

    // При выборе даты отправления
    dateFromInput.addEventListener('change', function() {
        const selectedDate = this.value;

        if (selectedDate) {
            logger.debug('Выбрана дата отправления', { date: selectedDate, form: formType });

            // Устанавливаем минимальную дату возвращения = дата отправления
            dateToInput.min = selectedDate;

            // Если дата возвращения раньше даты отправления или не выбрана - ставим ту же дату
            if (!dateToInput.value || dateToInput.value < selectedDate) {
                dateToInput.value = selectedDate;
            }

            // Автоматически фокусируемся на поле даты возвращения
            setTimeout(() => {
                dateToInput.focus();
                dateToInput.click(); // Открываем календарь
            }, 100);
        }
    });

    // При выборе даты возвращения - валидация
    dateToInput.addEventListener('change', function() {
        const dateFrom = dateFromInput.value;
        const dateTo = this.value;

        if (dateFrom && dateTo && dateTo < dateFrom) {
            showNotification('Дата возвращения не может быть раньше даты отправления!', 'error');
            this.value = '';
            logger.warn('Invalid date_to selected', { dateFrom, dateTo });
        } else if (dateFrom && dateTo) {
            // Рассчитываем количество дней
            const days = Math.ceil((new Date(dateTo) - new Date(dateFrom)) / (1000 * 60 * 60 * 24)) + 1;
            logger.debug('Дата возвращения выбрана', { dateFrom, dateTo, days });

            // Показываем визуальную подсказку о количестве дней
            showDateRangeSummary(dateFromInput, dateToInput, days);
        }
    });

    // Подсветка при фокусе
    dateFromInput.addEventListener('focus', function() {
        this.style.borderColor = '#42A5F5';
        this.style.boxShadow = '0 0 0 3px rgba(66, 165, 245, 0.1)';
    });

    dateFromInput.addEventListener('blur', function() {
        this.style.borderColor = '#e0e0e0';
        this.style.boxShadow = 'none';
    });

    dateToInput.addEventListener('focus', function() {
        this.style.borderColor = '#42A5F5';
        this.style.boxShadow = '0 0 0 3px rgba(66, 165, 245, 0.1)';
    });

    dateToInput.addEventListener('blur', function() {
        this.style.borderColor = '#e0e0e0';
        this.style.boxShadow = 'none';
    });
}

/**
 * Показывает краткую информацию о выбранном диапазоне дат
 * @param {HTMLInputElement} dateFromInput
 * @param {HTMLInputElement} dateToInput
 * @param {number} days - Количество дней
 */
function showDateRangeSummary(dateFromInput, dateToInput, days) {
    // Ищем или создаем элемент для подсказки
    let summaryElement = dateToInput.parentElement.querySelector('.date-range-summary');

    if (!summaryElement) {
        summaryElement = document.createElement('div');
        summaryElement.className = 'date-range-summary';
        summaryElement.style.cssText = `
            margin-top: 8px;
            padding: 8px 12px;
            background: #E3F2FD;
            border-left: 3px solid #42A5F5;
            border-radius: 4px;
            font-size: 13px;
            color: #1976D2;
            animation: fadeIn 0.3s;
        `;
        dateToInput.parentElement.appendChild(summaryElement);
    }

    const dateFrom = new Date(dateFromInput.value);
    const dateTo = new Date(dateToInput.value);

    const dateFromFormatted = dateFrom.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
    const dateToFormatted = dateTo.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });

    summaryElement.innerHTML = `
        📅 <strong>${dateFromFormatted}</strong> → <strong>${dateToFormatted}</strong>
        <span style="margin-left: 10px; color: #66BB6A;">✓ ${days} ${getDaysWord(days)}</span>
    `;

    // Автоматически скрываем через 3 секунды
    setTimeout(() => {
        if (summaryElement) {
            summaryElement.style.animation = 'fadeOut 0.3s';
            setTimeout(() => summaryElement.remove(), 300);
        }
    }, 3000);
}

/**
 * Возвращает правильное склонение слова "день"
 * @param {number} days
 * @returns {string}
 */
function getDaysWord(days) {
    const lastDigit = days % 10;
    const lastTwoDigits = days % 100;

    if (lastTwoDigits >= 11 && lastTwoDigits <= 19) {
        return 'дней';
    }

    if (lastDigit === 1) {
        return 'день';
    }

    if (lastDigit >= 2 && lastDigit <= 4) {
        return 'дня';
    }

    return 'дней';
}
