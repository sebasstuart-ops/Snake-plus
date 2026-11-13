
import sys
import re
import json

CLAVES_NIVEL = ('SPEED', 'NEXT_AT', 'POISON', 'INVULNERABLE', 'CLOUDS', 'NYAN')

FORMAS_VALIDAS = ('RECTANGULAR', 'CIRCULAR', 'TRIANGULAR')


def lexer(codigo_fuente):
    codigo_fuente = re.sub(r'(?m)(^|\s)#(?![0-9A-Fa-f]{6}\b).*', ' ', codigo_fuente)
    token_regex = (r'#[0-9A-Fa-f]{6}\b'          
                   r'|\b[A-F0-9]{6}\b'           
                   r'|\b[A-Z][A-Z0-9_]*\b'      
                   r'|\d+'                      
                   r'|[\[\](),:]')               
    return re.findall(token_regex, codigo_fuente)

class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.posicion = 0          
        self.ast = {
            "tipo_juego": None,
            "config": {},
            "shapes": {},
            "events": {},
            "shape_attrs": {},      
            "powerups": {}      
        }

    def parse(self):

        while self.posicion < len(self.tokens):
            t = self.tokens[self.posicion]
            if t == 'GAME_TYPE':
                self.parsear_tipo_juego()
            elif t == 'GAME_GRID':
                self.parsear_grid()
            elif t == 'GAME_COLOR':
                self.consumir('GAME_COLOR')
                self.ast['config']['color'] = self.consumir()
            elif t == 'DEFINE':
                self.parsear_definicion()
            elif t == 'LEVELS':            
                self.parsear_levels()
            elif t == 'ON':
                self.parsear_evento()
            else:
                self.posicion += 1        
        if self.ast['tipo_juego'] != 'TETRIS':
            del self.ast['powerups']
            if not self.ast['shape_attrs']:
                del self.ast['shape_attrs']
        return self.ast

    def actual(self):
        if self.posicion < len(self.tokens):
            return self.tokens[self.posicion]
        return None

    def consumir(self, esperado=None):
        if self.posicion < len(self.tokens):
            token = self.tokens[self.posicion]
            if esperado and token != esperado:
                raise Exception("Error de sintaxis: Se esperaba '" + esperado +
                                "' pero se encontro '" + token + "'")
            self.posicion += 1
            return token
        if esperado:
            raise Exception("Error de sintaxis: Se esperaba '" + esperado +
                            "' pero se llego al final del archivo.")
        return None

    def consumir_numero(self, contexto):
        t = self.consumir()
        if t is None or not t.isdigit():
            raise Exception("Error de sintaxis: se esperaba un numero en " +
                            contexto + " pero se encontro '" + str(t) + "'")
        return int(t)

    def normalizar_color(self, c):
        return c if c.startswith('#') else '#' + c

    def parsear_tipo_juego(self):
        self.consumir('GAME_TYPE')
        self.ast['tipo_juego'] = self.consumir()

    def parsear_grid(self):
        self.consumir('GAME_GRID')
        self.consumir('(')
        ancho = int(self.consumir())
        self.consumir(',')
        alto = int(self.consumir())
        self.consumir(')')
        self.ast['config']['grid_size'] = [ancho, alto]

    def parsear_estados(self):
        estados = []
        while self.actual() == 'STATE':
            self.consumir('STATE')
            self.consumir()               
            self.consumir(':')
            matriz = []
            while self.actual() == '[':
                fila = []
                self.consumir('[')
                while self.actual() != ']':
                    fila.append(int(self.consumir()))
                    if self.actual() == ',':
                        self.consumir(',')
                self.consumir(']')
                matriz.append(fila)
            estados.append(matriz)
        return estados

    def parsear_definicion(self):
        self.consumir('DEFINE')
        tipo = self.consumir()
        if tipo == 'SHAPE':
            self.parsear_shape()
        elif tipo == 'POWERUP':
            self.parsear_powerup()
        else:
            raise Exception("Error de sintaxis: Se esperaba 'SHAPE' o 'POWERUP' "
                            "despues de DEFINE, se encontro '" + str(tipo) + "'")

    def parsear_shape(self):
        nombre = self.consumir()
        self.consumir(':')
        attrs = {"color": "#00FFFF", "chance": 1}
        explicitos = {}
        while self.actual() in ('COLOR', 'CHANCE', 'FORM'):
            clave = self.consumir()
            self.consumir(':')
            valor = self.consumir()
            if clave == 'COLOR':
                attrs['color'] = explicitos['color'] = self.normalizar_color(valor)
            elif clave == 'CHANCE':
                attrs['chance'] = explicitos['chance'] = int(valor)
            else:                                   # FORM
                if valor not in FORMAS_VALIDAS:
                    raise Exception("Error de sintaxis: FORM debe ser RECTANGULAR, "
                                    "CIRCULAR o TRIANGULAR, se encontro '" + str(valor) + "'")
                attrs['form'] = explicitos['form'] = valor
        estados = self.parsear_estados()
        self.consumir('END')
        self.ast['shapes'][nombre] = estados
        if self.ast['tipo_juego'] == 'TETRIS':
            self.ast['shape_attrs'][nombre] = attrs
        elif explicitos:
            self.ast['shape_attrs'][nombre] = explicitos

    def parsear_powerup(self):
        nombre = self.consumir()
        self.consumir(':')
        pu = {"puntos": 0, "color": "#FFFFFF"}
        while self.actual() in ('COLOR', 'EFFECT', 'POINTS', 'TRIGGER_LINES', 'TRIGGER_ROTATE'):
            clave = self.consumir()
            self.consumir(':')
            if clave == 'COLOR':
                pu['color'] = self.normalizar_color(self.consumir())
            elif clave == 'EFFECT':
                pu['efecto'] = self.consumir()
            elif clave == 'POINTS':
                pu['puntos'] = int(self.consumir())
            elif clave == 'TRIGGER_LINES':
                pu['trigger_lineas'] = int(self.consumir())
            elif clave == 'TRIGGER_ROTATE':
                shape = self.consumir()
                veces = int(self.consumir())
                pu['trigger_rotacion'] = {"shape": shape, "veces": veces}
        pu['estados'] = self.parsear_estados()
        self.consumir('END')
        self.ast['powerups'][nombre] = pu

    def parsear_levels(self):
        self.consumir('LEVELS')
        self.consumir(':')
        niveles = []
        while self.actual() == 'LEVEL':
            self.consumir('LEVEL')
            nivel = {'nombre': self.consumir()}
            self.consumir(':')
            while self.actual() != 'END':
                if self.actual() is None:
                    raise Exception("Error de sintaxis: falta 'END' al final del nivel " +
                                    nivel['nombre'])
                clave = self.consumir()
                if clave not in CLAVES_NIVEL:
                    raise Exception("Error de sintaxis: atributo de nivel desconocido '" +
                                    clave + "' en el nivel " + nivel['nombre'])
                self.consumir(':')
                nivel[clave.lower()] = self.consumir_numero(clave + " del nivel " + nivel['nombre'])
            self.consumir('END')                   
            if nivel.get('speed', 1) <= 0:
                raise Exception("Error: SPEED del nivel " + nivel['nombre'] + " debe ser mayor que 0")
            niveles.append(nivel)
        if not niveles:
            raise Exception("Error de sintaxis: LEVELS debe contener al menos un LEVEL")
        self.consumir('END')                       
        self.ast['levels'] = niveles                

    def parsear_evento(self):
        self.consumir('ON')
        nombre_evento = 'ON_' + self.consumir()
        self.consumir(':')
        acciones = []
        fin_accion = ['END', 'ON', 'DEFINE', 'SPAWN', 'MOVE', 'ROTATE',
                      'INCREASE_SCORE', 'SET_DIRECTION', 'GROW', 'GAME_OVER']
        while self.posicion < len(self.tokens) and self.actual() != 'END':
            verbo = self.consumir()
            if verbo == 'GAME_OVER':
                acciones.append({'accion': verbo, 'objeto': None, 'params': []})
                continue
            objeto = self.consumir()
            params = []
            if self.actual() == 'AT':
                self.consumir('AT')
                if self.actual() == 'RANDOM':
                    params.append(self.consumir())
                else:
                    self.consumir('(')
                    x = int(self.consumir())
                    self.consumir(',')
                    y = int(self.consumir())
                    self.consumir(')')
                    params.append([x, y])
            elif self.actual() is not None and self.actual() not in fin_accion:
                params.append(self.consumir())
            acciones.append({'accion': verbo, 'objeto': objeto, 'params': params})
        self.consumir('END')
        self.ast['events'][nombre_evento] = acciones

def generar_codigo(ast, archivo_salida):
    f = open(archivo_salida, 'w')
    try:
        json.dump(ast, f, indent=2)
    finally:
        f.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python compiler.py <archivo_entrada.brick>")
        sys.exit(1)
    archivo_entrada = sys.argv[1]
    archivo_salida = archivo_entrada.replace('.brick', '.json')
    print("Compilando " + archivo_entrada + "...")
    try:
        f = open(archivo_entrada, 'r')
        try:
            codigo = f.read()
        finally:
            f.close()
        ast = Parser(lexer(codigo)).parse()
        generar_codigo(ast, archivo_salida)
        print("Compilacion exitosa! Archivo de juego creado en " + archivo_salida)
    except Exception as e:
        print("\n!!! ERROR DE COMPILACION !!!")
        print(str(e))
        sys.exit(1)
