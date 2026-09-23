"""Lower validated expressions into bounded native DAG instructions."""
import ast,math
from .behavioral import compile_behavioral_expression


def program(expression):
    compiled=compile_behavioral_expression(expression.split('=',1)[1] if expression[:2].upper() in ('V=','I=') else expression)
    instructions=[]
    def emit(op,a=-1,b=-1,c=-1,value=0.):
        instructions.append(f'{op} {a} {b} {c} {value:.17g}')
        if len(instructions)>512:raise ValueError('Native behavioral program exceeds 512 instructions')
        return len(instructions)-1
    def walk(node):
        if isinstance(node,ast.Expression):return walk(node.body)
        if isinstance(node,ast.Constant):return emit('const',value=float(node.value))
        if isinstance(node,ast.Name):
            if node.id=='time':return emit('time')
            return emit('const',value={'pi':math.pi,'e':math.e}[node.id]) if node.id in ('pi','e') else emit('signal',value=int(node.id[3:]))
        if isinstance(node,ast.UnaryOp):return walk(node.operand) if isinstance(node.op,ast.UAdd) else emit('neg',walk(node.operand))
        if isinstance(node,ast.BinOp):return emit({ast.Add:'add',ast.Sub:'sub',ast.Mult:'mul',ast.Div:'div',ast.Mod:'mod',ast.Pow:'pow'}[type(node.op)],walk(node.left),walk(node.right))
        if isinstance(node,ast.Compare):return emit({ast.Gt:'gt',ast.GtE:'ge',ast.Lt:'lt',ast.LtE:'le'}[type(node.ops[0])],walk(node.left),walk(node.comparators[0]))
        if isinstance(node,ast.Call):
            name=node.func.id
            if name=='table':
                x=walk(node.args[0]);pairs=[]
                for i in range(1,len(node.args),2):
                    try:point=float(ast.literal_eval(node.args[i]))
                    except (ValueError,TypeError):raise ValueError('Native table breakpoints must be literal constants')
                    if pairs and point<=pairs[-1][0]:raise ValueError('Table breakpoints must increase')
                    pairs.append((point,walk(node.args[i+1])))
                result=pairs[-1][1]
                for i in range(len(pairs)-2,-1,-1):
                    lo,yl=pairs[i];hi,yh=pairs[i+1]
                    fraction=emit('div',emit('sub',x,emit('const',value=lo)),emit('const',value=hi-lo))
                    segment=emit('add',yl,emit('mul',fraction,emit('sub',yh,yl)))
                    result=emit('if',emit('lt',x,emit('const',value=hi)),segment,result)
                return emit('if',emit('lt',x,emit('const',value=pairs[0][0])),pairs[0][1],result)
            args=[walk(a) for a in node.args]
            return emit('if' if name=='spice_if' else name,*args)
        raise ValueError('Unsupported native behavioral syntax')
    walk(compiled.tree)
    signals='\n'.join(f'{s.kind} {s.first} {s.second}' for s in compiled.signals)
    return '\n'.join(instructions),signals
