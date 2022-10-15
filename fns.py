#*- coding: utf-8 -*-
import io
import re
import json
import requests
from time import sleep
import pdfminer.high_level
import logging
class FNS(object):
    """Получение информации из реестра ФНС

        type - 'ul', 'ip' ,'fl'
        title_long - 'Общество с Ограниченной Ответственностью "СПЕЦСТРОЙ"'
        title_short - 'ООО "СПЕЦСТРОЙ"'
        position - 'Директор'
        fio - 'Степанов Алексей Геннадьевич'
        address - '194358, САНКТ-ПЕТЕРБУРГ ГОРОД, УЛИЦА ШОСТАКОВИЧА,  3,  1,  ЛИТ.А ПОМЕЩЕНИЕ 8-Н'
        inn - '7802182340'
        ogrn - '1027801558487'
        kpp - '780201001'
        reg_date - '25.11.2002'
        end_date - '', окончание деятельности
        not_valid_date - '',  данные не валидны с даты
        doc_token - 'C3C224...CB2A61F41'
        dirs - если несколько директоров {0: {'position': 'Директор', 'fio': 'Плотников Александр Михайлович'}, 1: {'position': 'Президент', 'fio': 'Юсупов Рафаэль Мидхатович'}}
        dirs_raw - 'Директор: Степанов Алексей Геннадьевич'

        dict - словарь со всеми полученными значениями

        is_doc_loaded - загружен ли ранее pdf выписка по данной организации
        doc_pdf - бинарное содержимое pdf документа

        is_one_record - одна запись результат?
        is_valid_org - результат проверки на недостоверность сведений об организации
        response_act_num - количество действующих организаций
    """

    _URL_BASE = 'https://egrul.nalog.ru'
    _URL_GET_DATA = _URL_BASE + '/search-result/'
    _URL_GET_DOC_REQUEST = _URL_BASE + '/vyp-request/'
    _URL_GET_DOC_STATUS = _URL_BASE + '/vyp-status/'
    _URL_GET_DOC_DOWNLOAD = _URL_BASE + '/vyp-download/'
    _UNRELIABLE_MARK =  'недостоверн'


    def __init__(self, inn=None, selecte_one=True, proxy=None):
        """
            inn : строка с инн или огрн для поиска организации
            если inn заполнен выполняется метод info и заполняются поля объекта
        """
        self.log = logging.getLogger('FNS')
        self.log.debug('[FNS] inn=%s selecte_one=%s proxy=%s' % (inn, selecte_one, proxy))
        self._reset_variables()
        self.session = requests.Session()
        if proxy:
            self.session.proxies.update(proxy)
            self.session.trust_env = False
                
        if inn:
            self.info(inn, selecte_one=selecte_one)   # get_data
                    
    def _reset_variables(self):
        self.type = ''
        self.title_long = ''
        self.title_short = ''
        self.position = ''
        self.fio = ''
        self.fio_f = ''
        self.fio_i = ''
        self.fio_o = ''
        self.address = ''
        self.inn = ''
        self.ogrn = ''
        self.kpp = ''
        self.reg_date = ''
        self.end_date = ''
        self.not_valid_date = ''
        self.doc_token = ''
        self.dirs_raw = ''
        self.dirs = {}
        self.dirs_num = 0
        self.dict = {}
        self.is_one_record = False
        self.is_doc_loaded = False
        self.doc_pdf = b''
        self.is_valid_org = None

# +++  проверить переменные ниже

        self.response_raw = ''
        self._response = ''
        self.response_num = 0
        self.response_act = ''
        self.response_act_num = 0

# +++ сделать метод сырой поиск, поиск с выводом действующих организаций

    def info(self, inn, selecte_one=True, attempts=10):
        """
            Получает данные по организации по ИНН/ОГРН.
            attempts - количество попыток получить данные, попытки разделены ожиданием *10c
            selecte_one - заполнять данные по одной организации выбирается действующая если есть, иначе первая в выдаче
        """
        self._reset_variables()

        self.response_raw = self._get_response(inn, attempts)
        self.response_act = self._acting_records(self.response_raw)
        # print('self.response_act', self.response_act) 
        self.response_act_num = len(self.response_act)

        if self.response_act_num >1:
            print('*** warning : более одной действующей организации') 
            self.log.warning('[fns] more then 1 organisation' )
                

        if self.response_num > 1: 
            if selecte_one:
                if self.response_act_num >= 1:
                    self._response = self.response_act[0]
                else:
                    self._response = self.response_raw[0]
            else:
                return

        elif self.response_num == 1:
            self._response = self.response_raw[0]
            self.is_one_record = True
            

        if not self._response:
            print('Отсутствую данные ФНС') 
            self.log.warning('[fns] empty response' )

            return

        if self._response['k'] == 'ul':
            self.type = 'ul'
        elif self._response['k'] == 'fl':
            self.type = 'ip'
        elif self._response['k'] == 'sprav-fl':
            self.type = 'fl'
        else:
            self.type = 'unknown'

        self.doc_token = self._response['t']
        
        if self.type == 'fl':
            return

        self.title_long = self._response.get('n','')
        self.title_short = self._response.get('c','')
        self.address = self._response.get('a','')
        self.inn = self._response.get('i','')
        self.ogrn = self._response.get('o','')
        self.kpp = self._response.get('p','')
        self.reg_date = self._response.get('r','')
        self.end_date = self._response.get('e','')
        self.not_valid_date = self._response.get('v','')


        if self._response['k'] == 'ul':
            if 'g' in self._response:
                self.dirs_raw = self._response['g']

                # случай с несколькими директорами
                if ',' in self._response['g'] and self._response['g'].count(':') > 1:
                    self.dirs = self._dirs_dict(self._response['g'])
                    
                    # берем первого директора
                    self.fio = self.dirs[0]['fio']
                    self.position = self.dirs[0]['position']
                else:
                    # self.position = self._response['g'].split(':')[0].strip()
                    self.position = self._response['g'].split(':')[0].strip()
                    self.dirs_num = 1
                    try:
                        self.fio = self._response['g'].split(':')[1].strip()
                    except Exception as e:
                        self.fio = self._response['g'] 
            else:
                print('*** error : отсутствует поле должность и ФИО')
                self.log.warning('[fns] no position and fio fields' )
                self.log.warning('[fns] _response = %s' % self._response)
                self.position = ''

        # если не юр лицо берем фио
        else:
            if 'n' in self._response:
                self.fio = self._response['n']

        # if (self._response['k'] == 'ul') and ('g' in self._response):

            # if ',' in self._response['g'] and self._response['g'].count(':') > 1:

            # self.fio = self._response['g'].split(',')[0].split(':')[1].strip()

        self.fio_f, self.fio_i, self.fio_o = self.fio_split(self.fio)

        
        self._write_dict()



    def _get_response(self, query, attempts=10):
        """
            Метод получает данные по запросу
            attempts - количество попыток получить данные, попытки разделены ожиданием №*10
        """

        attempt_counter = 0
        sleep(1)  # пауза перед запросом, чтобы не получить на капчу
        while attempt_counter < attempts:  # отправляем запрос
            attempt_counter += 1
            _req1 = self.session.post(self._URL_BASE, data={'query':str(query) })
            
            try:
                j1 = json.loads(_req1.text)  # что вернет
            except Exception as e:
                j1 = {}
                print('*** error : Не удалось загрузить json self._get_response', _req1.text) 
                self.log.error(f'[fns] Не удалось загрузить json self._get_response {_req1.text}')


            if _req1.status_code != requests.codes.ok :
                print('*** error : ошибка ОТПРАВКИ запроса в nalog.ru. код ошибки', _req1.status_code)  
                self.log.error('[fns] ошибка ОТПРАВКИ запроса в nalog.ru. код ошибки = %s' % _req1.status_code)


                if _req1.status_code == requests.codes.not_allowed :
                    print('*** error : Сервис nalog.ru не доступен. данные не получены') 
                    self.log.error('[fns] Сервис nalog.ru не доступен. данные не получены')
                    return {}

                if ('ERRORS' in j1) and ('captchaSearch' in j1['ERRORS']):
                    print('ФНС запрашивает ввод капчи, ждем ...', attempt_counter*10, 'c')
                    self.log.warning('[fns] ФНС запрашивает ввод капчи, ждем ... %s*10 c' % attempt_counter)
                    sleep(attempt_counter*10)
                else:
                    print('Ошибка. ответ сервера =', j1) 
                    self.log.error('[fns] ФОшибка. ответ сервера = %s' % j1)

            elif j1.get('captchaRequired') != False: # запрашивается капча - ждем
                print('ФНС запрашивает ввод капчи, ждем ...', attempt_counter*10, 'c')
                self.log.warning('[fns] ФНС запрашивает ввод капчи, ждем ... %s*10 c' % attempt_counter)
                sleep(attempt_counter*10)
            else:
                break # данные получены без ошибок - выходим из цикла


        attempt_counter = 0
        while attempt_counter < attempts:
            try:
                _req2 = self.session.get(self._URL_GET_DATA + j1['t'])
            except Exception as e:
                print('error =', _req2.status_code)
                self.log.error('[fns] error = %s' % _req2.status_code)
                # print(json.loads(_req2.text))  # что вернет
                
            if _req2.status_code != requests.codes.ok :
                print('*** error : ошибка ПОЛУЧЕНИЯ ответа из nalog.ru. код ошибки', _req2.status_code)
                self.log.error('[fns] ошибка ПОЛУЧЕНИЯ ответа из nalog.ru. код ошибки = %s' % _req2.status_code)
                print(json.loads(_req2.text)) 
                break    # точно return?
            j2 = json.loads(_req2.text)
            if j2 == dict(status = 'wait'):
                print('Ждем ответ ФНС ...') 
                self.log.info('[fns] Ждем ответ ФНС ...')
                attempt_counter += 1
                sleep(attempt_counter*10)
                continue
            
            self.response_num = len(j2.get('rows'))

            if not j2.get('rows') :
                print('*** error : ошибка доступа к структуре ответа ФНС. отсутствует ключ ["rows"]')
                self.log.error('[fns] ошибка доступа к структуре ответа ФНС. отсутствует ключ ["rows"]')
                break
            elif len(j2.get('rows')) != 1:
                # print('Найдено записей ЕГРН =', len(j2.get('rows')))
                return j2['rows']

            return j2['rows'] # если одна запись возвращаем не список, а сам словарь
            # return j2['rows'][0] # если одна запись возвращаем не список, а сам словарь
        return []


    def _acting_records(self, list_of_dicts):

        actual_list_of_dicts = []
        if len(list_of_dicts) == 1 and list_of_dicts[0].get('tot') == '0':
            return []

        if type(list_of_dicts) == list:
            for i in range(0, len(list_of_dicts)):
                if not ('e' in list_of_dicts[i] or 'v' in list_of_dicts[i]) : 
                    actual_list_of_dicts.append(list_of_dicts[i])
            
            return actual_list_of_dicts

        elif type(list_of_dicts) == dict:
            return list_of_dicts  # +++ убрать

    def _first_record(self, list_of_dicts):

        if type(list_of_dicts) == list:
            return list_of_dicts[0]


    def search(self, query):
        """
            Возвращает список со словарями с результатами поискового запроса по любым данным
        """
        return self._get_response(query)



# ----------------

    def get_doc_pdf(self, attempts=10):
        """
            Возвращает битовую строку с содержимым выписки в формате pdf
            attempts - количество попыток получить данные, попытки разделены ожиданием №*10
        """

        self.is_doc_loaded = False
        self.doc_pdf = b''

        sleep(5)

        attempt_counter = 0
        while attempt_counter < attempts:
            attempt_counter += 1 
            _req1 = self.session.get(self._URL_GET_DOC_REQUEST + self.doc_token) #отправка запроса на выписку
            # print('get_doc_pdf ответ на запрос выписки', _req1.text) 
            j1 = json.loads(_req1.text)

            if j1.get('captchaRequired') == True: # запрашивается капча - ждем
                print('ФНС запрашивает ввод капчи [get_doc_pdf], ждем ...', attempt_counter*10, 'c')
                self.log.warning('[fns] [get_doc_pdf] ФНС запрашивает ввод капчи, ждем ... %s*10 c' % attempt_counter)

                sleep(attempt_counter*10)
                continue
            
            if 'ERRORS' in j1:
                if 'captchaVyp' in j1['ERRORS']:
                    print('Отправка запроса на выписку ФНС [get_doc_pdf] (captcha) ...', attempt_counter*10, 'c') 
                    self.log.warning('[fns] [get_doc_pdf] Отправка запроса на выписку ФНС (captcha) ... ... %s*10 c' % attempt_counter)
                    sleep(attempt_counter*10)
                    continue
                else:
                    print('Отправка запроса на выписку ФНС. [get_doc_pdf] неизвестная ошибка ', j1)
                    self.log.error('[fns] [get_doc_pdf] Отправка запроса на выписку ФНС. неизвестная ошибка %s' % j1)
            else:
                break


        attempt_counter = 0
        while attempt_counter < attempts:
            attempt_counter += 1 
            _req2 = self.session.get(self._URL_GET_DOC_STATUS + self.doc_token) # статус зщапроса на выписку

            try:
                j2 = json.loads(_req2.text)['status']
            except Exception as e:
                j2 = ''
                print(_req2.text) 
                self.log.warning('[fns] [get_doc_pdf] ошибка получения статуса выписки. %s' % _req2.text)

            if j2 == 'ready': # ответ готов, выходим из цикла
                # print('выписка получена') 
                break

            if j2 == 'wait': 
                print('Ждем выписку ФНС [get_doc_pdf] ...', attempt_counter*10, 'c') 
                self.log.info('[fns] [get_doc_pdf] Ждем выписку ФНС ... %s*10 c' % attempt_counter)
                # print(r.text) 
                sleep(attempt_counter*10)
                continue
            print('необрабатываемый статус ответа ФНС [get_doc_pdf]', _req2.text)
            self.log.info('[fns] [get_doc_pdf] необрабатываемый статус ответа ФНС %s' % _req2.text)

        else:
            return b''
            self.log.warning('[fns] [get_doc_pdf] пустой ответ')

        _req3 = self.session.get(self._URL_GET_DOC_DOWNLOAD + self.doc_token) # получение выписки
        self.doc_pdf = _req3.content
        self.is_doc_loaded = True
        return self.doc_pdf
 

# ----------------

    def save_doc_pdf(self, filename):
        """
            Созраняет в указанный файл выписку в формате pdf
            filename - строка с полным путем к файлу
        """

        f = open(filename, 'wb')

        if self.is_doc_loaded:
            f.write(self.doc_pdf)
        elif self.doc_token:
            f.write(self.get_doc_pdf())

        f.close()

# ----------------


    def _write_dict(self):
        self.dict.update({'type' : self.type})
        self.dict.update({'title_long' : self.title_long})
        self.dict.update({'title_short' : self.title_short})
        self.dict.update({'position' : self.position})
        self.dict.update({'fio' : self.fio})
        self.dict.update({'address' : self.address})
        self.dict.update({'inn' : self.inn})
        self.dict.update({'ogrn' : self.ogrn})
        self.dict.update({'kpp' : self.kpp})
        self.dict.update({'reg_date' : self.reg_date})
        self.dict.update({'end_date' : self.end_date})
        self.dict.update({'not_valid_date' : self.not_valid_date})
        # self.dict.update({'doc_token' : self.doc_token})

        if self.dirs:
            self.dict.update({'dirs' : self.dirs})

        self.dict.update({'dirs_raw' : self.dirs_raw})
        self.dict.update({'dirs_num' : self.dirs_num})
        
        self.dict.update({'is_doc_loaded' : self.is_doc_loaded})

        if self.is_valid_org != None:
            self.dict.update({'is_valid_org' : self.is_valid_org})
        self.dict.update({'response_act_num' : self.response_act_num})


    def fio_split(self, fio):
        """
            Разбивает ФИО на 3 составляющие
            fio_f, fio_i, fio_o

            фамилия - первое слово
            имя - второе слово
            отчество - третье слово и последующие
        """
        
        fio_parts = ' '.join(fio.split()).split()
        fio_parts_num = len(fio_parts)

        fio_f = fio_parts[0] if fio_parts_num >= 1 else ''
        fio_i = fio_parts[1] if fio_parts_num >= 2 else ''
        fio_o = ' '.join(fio_parts[2:]) if fio_parts_num >= 3 else ''
        return fio_f, fio_i, fio_o


    def is_valid_org_check(self, attempts=10, pages_to_parse=4):
        """
            Возвращает False если в ЕГРЮЛ есть отметка о недостоверности данных (адреса / прочего)
            Проверяет наличие слова "недостоверн" в выписке ЕГРЮЛ в первых 3 страницах
        """
        self.is_valid_org = None

        if not self.is_doc_loaded:
            # self.get_doc_pdf(self.doc_token)
            self.get_doc_pdf(attempts)

        if self.doc_pdf:
            self.pdf_data = io.BytesIO(self.doc_pdf)
            self.pdf_text = pdfminer.high_level.extract_text(self.pdf_data, maxpages=pages_to_parse)
            self.pdf_text_cut = re.sub(r'[ \f\n\r\t\v]','',self.pdf_text)

            if self.type == 'ul':
                if self._UNRELIABLE_MARK in self.pdf_text_cut:
                    self.is_valid_org = False
                    self.dict.update({'is_valid_org' : self.is_valid_org})
                    return False
                else:
                    self.is_valid_org = True
                    self.dict.update({'is_valid_org' : self.is_valid_org})
                    return True
        else:
            print('ДАНЫЕ ВЫПИСКИ НЕ ПОЛУЧЕНЫ. проверка недостоверности не завершена') 





    def is_inn(self, inn):
        """
            Проверка строки на формат ИНН
            возвращвет True если выполняются все условия 
                - содержатся только цифры
                - длина 10 (ЮЛ) или 12 (ИП) цифр
                - начинается не с '00'

            :inn: инн на проверку
        """

        inn = str(inn)

        if inn.isdigit() and \
                not inn.startswith('00') and \
                ((len(inn) == 10) or (len(inn) == 12)) :

            return True
        else:
            print('*** error : NOT INN =', inn) 
            return False



    def _dirs_dict(self, director_string):
        """
            Возвращает список со словарями в случае нескольких директоров в организации
            каждый словарь содержит поля
            position, fio
        """

            # : разделяет должность и фио
            # , разделяет список руководителей (либо участвует в названии должности)

        result_list = []
        dirs_dict = {}

        temp_list = director_string.split(':') # 

        for i in range(0, len(temp_list)):
            if ( i == 0 ) or ( i == len(temp_list)-1 ):
                result_list.append(temp_list[i].strip())
            else:
                n = temp_list[i].index(',')   # ищем первый разделитель "," после фио 
                result_list.append(temp_list[i][:n].strip())
                result_list.append(temp_list[i][n+1:].strip())

        if len(result_list) % 2 != 0:  # должно быть четное количество элементов, пары (должность-фио)
            print('*** error: ошибка парсинга должностей и ФИО') 

        for i in range(0, len(result_list), 2):
            i_new = i // 2

            dirs_dict.update({i_new:{}})
            dirs_dict[i_new].update({'position' : result_list[i]})
            dirs_dict[i_new].update({'fio' : result_list[i+1]})

        self.dirs_num = len(result_list) // 2

        return dirs_dict


# ----------------

    def addr_cut(self, address):
        
        new_address = address
        cuts = []

        cuts.append([', ', '[РАЗДЕЛИТЕЛЬ]'])
        cuts.append([',', '[РАЗДЕЛИТЕЛЬ]'])
        cuts.append([' УЛИЦА ', '[УЛИЦА]'])
        cuts.append([' УЛ.', '[УЛИЦА]'])
        cuts.append([' ПР.', '[ПРОСПЕКТ]'])
        cuts.append([' ПРОСПЕКТ ', '[ПРОСПЕКТ]'])
        cuts.append([' ДОМ ', '[ДОМ]'])
        cuts.append([' Д.', '[ДОМ]'])
        cuts.append([' ГОРОД', '[ГОРОД]'])
        cuts.append([' ПОСЕЛОК ', '[ПОСЕЛОК]'])
        cuts.append([' П. ', '[ПОСЕЛОК]'])
        cuts.append([' ОФИС', '[ОФИС]'])
        cuts.append([' ОФ ', '[ОФИС]'])
        cuts.append([' ОФ.', '[ОФИС]'])
        cuts.append([' КОРПУС ', '[КОРПУС]'])
        cuts.append([' КОРП.', '[КОРПУС]'])
        # cuts.append([' К.', '[РАЗДЕЛИТЕЛЬ]'])
        cuts.append([' ПОМЕЩЕНИЕ ', '[ПОМЕЩЕНИЕ]'])
        cuts.append([' ПОМ ', '[ПОМЕЩЕНИЕ]'])
        cuts.append([' ПОМ. ', '[ПОМЕЩЕНИЕ]'])
        cuts.append([' ШОССЕ', '[ШОССЕ]'])
        cuts.append([' Ш.', '[ШОССЕ]'])
        cuts.append([' ГОРОД ', '[ГОРОД]'])
        cuts.append([' Г. ', '[ГОРОД]'])
        cuts.append([' КВАРТИРА ', '[КВАРТИРА]'])
        cuts.append([' КВ.', '[КВАРТИРА]'])
        cuts.append([' ЛИТЕРА ', '[ЛИТЕРА]'])
        cuts.append([' ЛИТЕР ', '[ЛИТЕРА]'])
        cuts.append([' ЛИТ.', '[ЛИТЕРА]'])
        cuts.append([' ЛИТ ', '[ЛИТЕРА]'])
        cuts.append([' КОМНАТА ', '[КОМНАТА]'])
        cuts.append([' КОМ.', '[КОМНАТА]'])
        cuts.append(['  ', ' '])
        # cuts.append('')
        # print(cuts) 

        for cut in cuts:
            new_address = new_address.replace(cut[0], cut[1])
            # print(new_address)

        new_address = new_address.replace('[РАЗДЕЛИТЕЛЬ]', ' ')
        new_address = new_address.replace('[ГОРОД]', ' ')

        return new_address





def find_fl_inn(fio_f, fio_i, fio_o, birthdate, doctype, docnumber, docdate):
    """
    docnumber="40 09 950176"
    """
    doc_type_code = {
        'passport_ussr' : '01',  # Паспорт гражданина СССР
        'birth_certificate' : '03', # Свидетельство о рождении
        'passport_foreign' : '10', # Паспорт иностранного гражданина
        'residence_permit' : '12', # Вид на жительство в России
        'residence_permit_temp' : '15', # Разрешение на временное проживание в России
        'asylum_certificate_temp' : '19', # Свидетельство о предоставлении временного убежища на территории России
        'passport_russia' : '21', # Паспорт гражданина России
        'birth_certificate_foreign' : '23', # Свидетельство о рождении, выданное уполномоченным органом иностранного государства
        'residence_permit_foreign' : '62', # Вид на жительство иностранного гражданина
        }

    url = 'https://service.nalog.ru/inn-proc.do'
    data = {
        'fam': fio_f,
        'nam': fio_i,
        'otch': fio_o,
        'bdate': birthdate,
        'bplace': '',
        'doctype': doc_type_code[doctype],
        'docno': docnumber,
        'docdt': docdate,
        'c': 'innMy',
        'captcha': '',
        'captchaToken': '',
    }

    try:
        resp = requests.post(url=url, data=data)
    except Exception as e:
        return {'code': 0, 'message' : f'Ошибка запроса к ФНС {e}'}

    if resp.status_code != requests.codes.ok :
        print('*** error : ошибка получения ответа. код ошибки =', resp.status_code) 
        # resp.raise_for_status()
        return {'code': 0, 'message' : f'код ошибки {resp.status_code}'}
    else:
        return resp.json()

    





# ------------------------------------------------


if __name__ == '__main__':
    inn = 920400134623
    fns = FNS(inn)
    print(fns.dict) 
