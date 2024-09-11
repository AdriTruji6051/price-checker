from subprocess import run, CREATE_NEW_CONSOLE
from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime
import threading
import json
from printer_mediator import  print_ticket
from printer_service import run_printer_service
import sqlite3
import socket

app = Flask(__name__)
CORS(app, supports_credentials=True)

#Variables globales 
PRINTERS_ON_WEB = {}

#Obtenemos las impresoras en el formato
def get_printers(ipv4):
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((ipv4, 12345))
    client_socket.sendall(b'GET PRINTERS')

    data = client_socket.recv(1024)
    client_socket.close()
    data = json.loads(data.decode('utf-8'))
    return data

def send_ticket_to_printer(ticket_struct = '', printer = {}, open_drawer = False):
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((printer['ipv4'], 12345))
    print_info = {
        'printerName': printer['name'],
        'text': ticket_struct,
        'openDrawer': open_drawer
    }

    print_info = json.dumps(print_info)
    client_socket.sendall(print_info.encode('utf-8'))

    data = client_socket.recv(1024)
    print(f"Respuesta del servidor: {data.decode()}")
    client_socket.close()

    return data.decode('utf-8')

#   Herramientas para las rutas del servidor
def calculate_total_bill(products) -> float:
    total_local = 0
    for key in products:
        IMPORTE = products[key]['IMPORTE']
        total_local += IMPORTE
    return total_local

def calculate_total_profit(products) -> float:
    total_profit = 0
    for key in products:
        IMPORTE = float(products[key]['IMPORTE'])
        COSTO_TOT = float(products[key]['CANTIDAD']) * float(products[key]['PCOSTO']) if  float(products[key]['PCOSTO']) > 0 else float(products[key]['MAYOREO'])
        total_profit += IMPORTE - COSTO_TOT
    return total_profit

def calculate_total_articles(products):
    total_article = 0
    for key in products:
        total_article += float(products[key]['CANTIDAD'])
    return total_article

def create_ticket_struct(products, change, notes, date):
    try:
        total_local = 0
        TICKET_TXT = str(f' Tel: 373 734 9861#-#    Cel: 33 1076 7498#-#    {date}#-#')

        if type(notes) != bool: TICKET_TXT += notes + '#-##-#----------------------------------------------->#-#' 
        else: TICKET_TXT += '#-#----------------------------------------------->#-#'

        for key in products:
            DESCRIPCION = products[key]['DESCRIPCION']
            PVENTA = products[key]['PVENTA']
            CANTIDAD = products[key]['CANTIDAD']
            IMPORTE = products[key]['IMPORTE']
            total_local += IMPORTE

            TICKET_TXT += str(CANTIDAD) + ' ' + str(DESCRIPCION) + '    ' + str(IMPORTE) + '#-# '
        
        TICKET_TXT += str(f'----------------------------------------------->#-##-#Total: {total_local}')
        TICKET_TXT += str(f'#-#Cambio:  {change}') if change else ' '
        TICKET_TXT += '#-##-#Gracias por su compra!...'

        return TICKET_TXT
    except Exception as e:
        print(e)

def sqlite3_query(query, params = [], commit = False) -> list:
    res = []
    conSQL = sqlite3.connect("./DB/data_base.sqlite3")
    cursorSQL = conSQL.cursor()
    rows = cursorSQL.execute(query, params)
    for row in rows:
        res.append(row)

    if(commit): conSQL.commit() 
    conSQL.close()

    return res

def product_to_json(row) -> dict:
    jsonRow = {
        'CODIGO': row[0],
        'DESCRIPCION': row[1],
        'TVENTA': row[2],
        'PCOSTO': row[3],
        'PVENTA': row[4],
        'DEPT': row[5],
        'MAYOREO': row[6],
        'IPRIORIDAD': row[7],
        'DINVENTARIO': row[8],
        'DINVMINIMO': row[9],
        'DINVMAXIMO': row[10],
        'CHECADO_EN': row[11],
        'PORCENTAJE_GANANCIA': row[12],
    }

    return jsonRow

def parse_paramas_to_array(data) -> list:
    params = [
        data.get('codigo'),
        data.get('descripcion'),
        data.get('tipoVenta'),
        data.get('pcosto'),
        data.get('pventa'),
        data.get('mayoreo'),
        data.get('dept'),
        data.get('prioridad'),
        data.get('inventarioActual'),
        data.get('inventarioMinimo'),
        data.get('inventarioMaximo'),
        data.get('checadoEn'),
        data.get('porcentaje_ganancia'),
    ]
    return params

#   GET SENTENCES
@app.route('/get/product', methods=['GET'])
def getProduct():
    res = None
    value = request.args.get('value')
    sql = "SELECT CODIGO, DESCRIPCION, TVENTA, PCOSTO, PVENTA, DEPT, MAYOREO, IPRIORIDAD, DINVENTARIO, DINVMINIMO, DINVMAXIMO, CHECADO_EN, PORCENTAJE_GANANCIA FROM PRODUCTOS WHERE CODIGO = ?"
    rows = sqlite3_query(sql, [value])
    
    for row in rows:
        res = row
        break
    
    if res:
        res = json.dumps(product_to_json(res))

    if not res:
        alreadyAdd = set()
        searchResults = []

        #Obtenemos los que coincidan al principio
        sql = "SELECT CODIGO, DESCRIPCION, TVENTA, PCOSTO, PVENTA, DEPT, MAYOREO, IPRIORIDAD, DINVENTARIO, DINVMINIMO, DINVMAXIMO, CHECADO_EN, PORCENTAJE_GANANCIA FROM PRODUCTOS WHERE DESCRIPCION LIKE ?"
        rowsPriority = sqlite3_query(sql,[f'{value}%'])
        
        for row in rowsPriority:
            alreadyAdd.add(row[0])
            jsonRow = product_to_json(row)
            searchResults.append(jsonRow)

        #Obtenemos todas las coincidencias y agregamos a los productos encontrados
        sql = "SELECT CODIGO, DESCRIPCION, TVENTA, PCOSTO, PVENTA, DEPT, MAYOREO, IPRIORIDAD, DINVENTARIO, DINVMINIMO, DINVMAXIMO, CHECADO_EN, PORCENTAJE_GANANCIA FROM PRODUCTOS WHERE DESCRIPCION LIKE ?"
        rowsComplementary = sqlite3_query(sql,[f'%{value}%'])

        for row in rowsComplementary:
            if row[0] not in alreadyAdd:
                jsonRow = product_to_json(row)
                searchResults.append(jsonRow)

        res = searchResults
            
    return jsonify({'product': res})

@app.route('/get/productById', methods=['GET'])
def getProductById():
    res = None
    value = request.args.get('value')
    sql = "SELECT CODIGO, DESCRIPCION, TVENTA, PCOSTO, PVENTA, DEPT, MAYOREO, IPRIORIDAD, DINVENTARIO, DINVMINIMO, DINVMAXIMO, CHECADO_EN, PORCENTAJE_GANANCIA FROM PRODUCTOS WHERE CODIGO = ?"
    rows = sqlite3_query(sql, [value])

    for row in rows:
        res = row
        break

    if res:
        res = json.dumps(product_to_json(res))
        
    return jsonify({'product': res})

#   PRODUCT CRUD LOGIC
@app.route('/insert/product', methods=['POST'])
def insertProduct():
    try:
        data = request.get_json()
        if data is None:
            return jsonify({'error': 'No se recibió ningún JSON'}), 400

        params = parse_paramas_to_array(data)

        sql = 'INSERT INTO PRODUCTOS (CODIGO, DESCRIPCION, TVENTA, PCOSTO, PVENTA, MAYOREO, DEPT, IPRIORIDAD, DINVENTARIO, DINVMINIMO, DINVMAXIMO, CHECADO_EN, PORCENTAJE_GANANCIA) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)'
        sqlite3_query(query= sql, params = params, commit= True)

        return jsonify({'status': 201})
    
    except Exception as e:
        print(e)
        return jsonify({'status': 409})

@app.route('/update/product', methods=['POST'])
def updateProduct():
    try:
        data = request.get_json()
        if data is None:
            return jsonify({'error': 'No se recibió ningún JSON'}), 400
        
        #codigo esta al principio, lo movemos al final
        params = parse_paramas_to_array(data)
        params.append(params.pop(0))
        print(params)

        sql = 'UPDATE PRODUCTOS SET DESCRIPCION = ?, TVENTA = ?, PCOSTO = ?, PVENTA = ?, DEPT = ?, MAYOREO = ?, IPRIORIDAD = ?, DINVENTARIO = ?, DINVMINIMO = ?, DINVMAXIMO = ?, CHECADO_EN = ?, PORCENTAJE_GANANCIA = ? WHERE CODIGO = ?;'
        sqlite3_query(query= sql, params = params, commit= True)

        return jsonify({'status': 201})
    
    except Exception as e:
        print(e)
        return jsonify({'status': 409})

@app.route('/delete/product', methods=['POST'])
def deleteProduct():
    try:
        data = request.get_json()
        if data is None:
            return jsonify({'error': 'No se recibió ningún JSON'}), 400

        params = [
            data.get('codigo')
        ]
    
        sql = 'DELETE FROM PRODUCTOS WHERE CODIGO = ?;'
        sqlite3_query(query= sql, params = params, commit= True)

        return jsonify({'status': 202})
    
    except Exception as e:
        print(e)
        return jsonify({'status': 409})
    
@app.route('/init/new', methods=['GET'])
def initPc():
    try:
        client_ip = request.remote_addr
        client_printers = get_printers(ipv4=client_ip)
        global PRINTERS_ON_WEB
        PRINTERS_ON_WEB.update(client_printers)
    except Exception as e:
        print(e)
    finally:
        return jsonify({'printers': 'loaded'})

#   TICKET PRINTER LOGIC
@app.route('/get/printers', methods=['GET'])
def getPrinters():
    printers = []
    for key in PRINTERS_ON_WEB:
        if PRINTERS_ON_WEB[key]['isdefault'] == True and PRINTERS_ON_WEB[key]['ipv4'] == request.remote_addr:
            printers.insert(0, key)
        elif PRINTERS_ON_WEB[key]['isdefault'] == True:
            printers.append(key)
        
    
    print(printers)
    return jsonify({'printers': printers})

#REFACTORIZAR LA SECCION DE TICKETS PARA QUE FUNCIONE CON LA VERSION DE RED
@app.route('/print/new/ticket', methods=['POST'])
def createTicket():
    try:
        data = request.get_json()
        if data is None:
            print('No data')
            return jsonify({'error': 'No se recibió ningún JSON'}), 400
        
        #Impresion del ticket
        willPrint = bool(data.get('print'))
        products = data.get('products')
        printerName = data.get('printerName')
        paidWith = float(data.get('change'))
        notes = data.get('notes')
        totalBill = calculate_total_bill(products)
        date = datetime.now()

        ticketStruct = create_ticket_struct(products = products,change = paidWith - totalBill, notes = notes, date=date.strftime('%Y-%m-%d %H:%M:%S'))
        printer = PRINTERS_ON_WEB[printerName]
        if willPrint : send_ticket_to_printer(ticket_struct=ticketStruct, printer=printer, open_drawer=True)

        #AQUI DEBEMOS CREAR LA ESTRUCTURA DEL TICKET Y GUARDARLO EN LA BD
        sql = 'SELECT MAX(ID), MAX(FOLIO) FROM VENTATICKETS'
        res = sqlite3_query(query = sql)
        

        for row in res:
            res = row
            break

        
        #DATOS PROVISIONALES, DEBEN SER DINAMICOS UNA VEZ SE COMPLETEN MAS PASOS DEL PROGRAMA....
        params = [
            res[0] + 1, #ID
            res[1] + 1, #FOLIO
            1, #CAJA_ID
            1, #CAJERO_ID
            'Ticket 1', #NOMBRE
            date.strftime('%Y-%m-%d %H:%M:%S.%f'), #CREADO_EN 
            calculate_total_bill(products), #SUBTOTAL
            0.0, #IMPUESTOS
            calculate_total_bill(products),  # TOTAL
            calculate_total_profit(products), # GANANCIA
            'f', # ESTA ABIERTO
            None, #CLIENTE_ID
            date.strftime('%Y-%m-%d %H:%M:%S'),  # VENDIDO_EN
            't', # ES MODIFICABLE
            paidWith,  # PAGO_CON
            'MXN', #MONEDA
            calculate_total_articles(products), #NUMERO_ARTICULOS
            date.strftime('%Y-%m-%d %H:%M:%S'),  # PAGADO EN
            'f', #ESTA CANCELADO
            '1000', #OPERACION_ID
            None, #OLD_TICKET_ID
            notes, #NOTAS
            't' if willPrint else 'f', # IMPRIMIR NOTA
            'e', #FORMA_PAGO
            None, #REFERENCIA
            None, #FACTURA_ID
            0.0 #TOTAL_DEVUELTO
        ]

        sql = 'INSERT INTO VENTATICKETS (ID, FOLIO, CAJA_ID, CAJERO_ID, NOMBRE, CREADO_EN, SUBTOTAL, IMPUESTOS, TOTAL, GANANCIA, ESTA_ABIERTO, CLIENTE_ID, VENDIDO_EN, ES_MODIFICABLE, PAGO_CON, MONEDA, NUMERO_ARTICULOS, PAGADO_EN, ESTA_CANCELADO, OPERACION_ID, OLD_TICKET_ID, NOTAS, IMPRIMIR_NOTA, FORMA_PAGO, REFERENCIA, FACTURA_ID, TOTAL_DEVUELTO) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);'
        sqlite3_query(query= sql, params = params, commit= True)

        sql = 'INSERT INTO VENTATICKETS_ARTICULOS (TICKET_ID, PRODUCTO_CODIGO, PRODUCTO_NOMBRE, CANTIDAD, GANANCIA, DEPARTAMENTO_ID, PAGADO_EN, USA_MAYOREO, PORCENTAJE_DESCUENTO, COMPONENTES, IMPUESTOS_USADOS, IMPUESTO_UNITARIO, PRECIO_USADO, CANTIDAD_DEVUELTA, FUE_DEVUELTO, PORCENTAJE_PAGADO) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);'
        for key in products:
            params = [
                res[0] + 1, #TICKET-ID
                products[key]['CODIGO'], # PRODUCTO-CODIGO
                products[key]['DESCRIPCION'], # PRODUCTO-NOMBRE
                products[key]['CANTIDAD'], # CANTIDAD
                float(products[key]['IMPORTE']) - float(products[key]['CANTIDAD']) * float(products[key]['PCOSTO']) if  float(products[key]['PCOSTO']) > 0 else float(products[key]['MAYOREO']), # GANANCIA
                None, # DEPARTAMENTO
                date.strftime('%Y-%m-%d %H:%M:%S'), # PAGADO-EN
                None, #USA-MAYOREO
                None, # PORCENTAJE-DESCUENTO
                None, # COMPONENTES
                None, # Impuestos usados
                None, # Impuestos unitarios
                float(float(products[key]['IMPORTE']) / float(products[key]['CANTIDAD'])), #PRECIO-USADO
                0,
                'f',
                0,
            ]
            sqlite3_query(query= sql, params = params, commit= True)
        
        return jsonify({'impresion': 'EXITOSA'})
    except Exception as e:
        print(e)
        return jsonify({'impresion': 'FALLIDA'})

@app.route('/get/ticket/day', methods=['GET'])
def getTicketDay():
    try:
        day =  request.args.get('day')
        sql = 'SELECT ID, FOLIO, TOTAL, PAGO_CON, NUMERO_ARTICULOS, PAGADO_EN, NOTAS FROM VENTATICKETS WHERE PAGADO_EN like ?;'
        rows = sqlite3_query(query=sql, params=[f'{day}%'])

        sql = 'SELECT PRODUCTO_CODIGO, PRODUCTO_NOMBRE, CANTIDAD, PRECIO_USADO FROM VENTATICKETS_ARTICULOS WHERE TICKET_ID = ?;'
        ticketsInfo = {}

        for row in rows:
            ticketID = row[0]
            date = row[5].split(' ')[1]
            ticketsInfo[ticketID] = {
                'id': row[0],
                'folio': row[1],
                'total': row[2],
                'pago_con': row[3],
                'articulos': row[4],
                'hour': date,
                'notes': row[6] if type(row[6]) != bytes else row[6].decode(encoding="utf-8"),
                'productos': sqlite3_query(query=sql, params=[ticketID]),
            } 
            
        return jsonify({'tickets': ticketsInfo})
    except Exception as e:
        print(e)
        return jsonify({'tickets': 'FALLIDO'})


@app.route('/print/ticket', methods=['POST'])
def rePrintTicket():
    try:
        data = request.get_json()
        if data is None:
            return jsonify({'error': 'No se recibió ningún JSON'}), 400
        
        ticket_id = data.get('id')
        printerName = data.get('printerName')
        

        #Obtenemos la informacion general del ticket
        sql = 'SELECT TOTAL, PAGO_CON, NOTAS, NUMERO_ARTICULOS, PAGADO_EN FROM VENTATICKETS WHERE ID = ?;'
        rows = sqlite3_query(query=sql, params=[ticket_id])[0]
        totalBill = rows[0]
        paidWith = rows[1]
        notes = rows[2]
        date = rows[4]

        #Obtenemos los productos que se vendieron en ese ticket
        sql = 'SELECT PRODUCTO_CODIGO, PRODUCTO_NOMBRE, PRECIO_USADO, CANTIDAD FROM VENTATICKETS_ARTICULOS WHERE TICKET_ID = ?;'
        rows = sqlite3_query(query=sql, params=[ticket_id])

        products = {}
        for row in rows:
            products[row[0]] = {
                'DESCRIPCION': row[1],
                'PVENTA': row[2],
                'CANTIDAD': row[3],
                'IMPORTE': row[2] * row[3],
            }

        ticketStruct = create_ticket_struct(products = products,change = paidWith - totalBill, notes = notes, date=date)
        print_ticket(text=ticketStruct, printer_name=printerName)
        return jsonify({'impresion': 'Correctamente!'}), 200
    except Exception as e:
        print(e)
        return jsonify({'impresion': 'Error!'})



#Fin de rutas de la API
def openHTML():
    run(['index.html'], shell=False, creationflags=CREATE_NEW_CONSOLE)

def startFlaskServer():
    app.run(debug=False,host='192.168.1.180', port=5000)

if __name__ == '__main__':
    printer_service = threading.Thread(target=run_printer_service)
    flaskServer = threading.Thread(target=startFlaskServer)
    html = threading.Thread(target=openHTML)
    
    printer_service.start()
    flaskServer.start()
    #html.start()