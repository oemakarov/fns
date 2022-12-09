import requests
from time import sleep

url_fl_inn_old = 'https://service.nalog.ru/inn-proc.do'
url_fl_inn_new = 'https://service.nalog.ru/inn-new-proc.do'

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



def find_fl_inn(fio_f, fio_i, fio_o, birthdate, doctype, docnumber, docdate):
    """
    docnumber="40 09 950176"
    """

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
        resp = requests.post(url=url_fl_inn_old, data=data)
    except Exception as e:
        return {'code': 0, 'message' : f'Ошибка запроса к ФНС {e}'}

    if resp.status_code != requests.codes.ok :
        print('*** error : ошибка получения ответа. код ошибки =', resp.status_code) 
        # resp.raise_for_status()
        return {'code': 0, 'message' : f'код ошибки {resp.status_code}'}
    else:
        return resp.json()



# -------------------------------------

def find_fl_inn_new(fio_f: str, fio_i: str, fio_o: str, birthdate: str, doctype: str, docnumber: str, docdate: str, attempts:int = 3, delay: int = 0.1):
    
    resp_q = _send_fl_inn_request(fio_f, fio_i, fio_o, birthdate, doctype, docnumber, docdate)
    request_id = resp_q.get('requestId')
    if not request_id:
        return None
    sleep(delay)

    while attempts:
        resp_a = _get_fl_inn_response(request_id)
        if not resp_a.get('inn'):
            sleep(delay)
            print(f'{attempts = }')
            attempts -= 1
        else:
            return resp_a['inn']


def _send_fl_inn_request(fio_f: str, fio_i: str, fio_o: str, birthdate: str, doctype: str, docnumber: str, docdate: str):
    """
    docnumber="40 09 950176"
    """
    data = {
        'fam': fio_f,
        'nam': fio_i,
        'otch': fio_o,
        'bdate': birthdate,
        'bplace': '',
        'doctype': doc_type_code[doctype],
        'docno': docnumber,
        'docdt': docdate,
        'c': 'find',
        'captcha': '',
        'captchaToken': '',
    }

    try:
        resp = requests.post(url=url_fl_inn_new, data=data)
    except Exception as e:
        return {'code': 0, 'message' : f'Ошибка запроса к ФНС {e}'}

    if resp.status_code != requests.codes.ok :
        print('*** error : ошибка получения ответа. код ошибки =', resp.status_code) 
        print('*** error : ошибка получения ответа. код ошибки =', resp.reason) 
        return {'code': 0, 'message' : f'код ошибки {resp.status_code}'}
    else:
        return resp.json()



def _get_fl_inn_response(request_id: str):

    data = {
                'c': 'get',
                'requestId': request_id,
    }
    try:
        resp = requests.post(url=url_fl_inn_new, data=data)
    except Exception as e:
        return {'code': 0, 'message' : f'Ошибка запроса к ФНС {e}'}

    if resp.status_code != requests.codes.ok :
        print('*** error : ошибка получения ответа. код ошибки =', resp.status_code) 
        return {'code': 0, 'message' : f'код ошибки {resp.status_code}'}
    else:
        return resp.json()








