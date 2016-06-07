"""
wire has the basic extended types useful for creating logic.

Types defined in this file include:
WireVector: the base class for ordered collections of wires
Input: a wire vector that receives an input for a block
Output: a wire vector that defines an output for a block
Const: a wire vector fed by a constant
Register: a wire vector that is latched each cycle
"""

from __future__ import print_function, unicode_literals

import numbers
import six

from . import core  # needed for _setting_keep_wirevector_call_stack

from .pyrtlexceptions import PyrtlError, PyrtlInternalError
from .core import working_block, next_constvar_name, next_tempvar_name, LogicNet

# ----------------------------------------------------------------
#        ___  __  ___  __   __
#  \  / |__  /  `  |  /  \ |__)
#   \/  |___ \__,  |  \__/ |  \
#


class WireVector(object):
    """ The main class for describing the connections between operators.

    WireVectors act much like a list of wires, except that there is no
    "contained" type, each slice of a wirevector is itself a wirevector
    (even if it just contains a single "bit" of information).  The least
    significant bit of the wire is at index 0 and normal list slicing
    syntax applies (i.e. myvector[0:5] makes a new vector from the bottom
    5 bits of myvector, myvector[-1] takes the most significant bit, and
    myvector[-4:] takes the 4 most significant bits).
    """

    # "code" is a static variable used when output as string.
    # Each class inheriting from WireVector should overload accordingly
    _code = 'W'

    def __init__(self, bitwidth=None, name=None, block=None):
        """ Construct a generic WireVector

        :param int bitwidth: If no bitwidth is provided, it will be set to the
         minimum number of bits to represent this wire
        :param Block block: The block under which the wire should be placed.
         Defaults to the working block
        :param String name: The name of the wire referred to in some places.
         Must be unique. If none is provided, one will be autogenerated
        :return: a wirevector object representing a const wire
        """

        self._name = None
        self._block = working_block(block)
        # used only to verify the one to one relationship of wires and blocks
        self.name = next_tempvar_name(name)
        self._validate_bitwidth(bitwidth)

        if core._setting_keep_wirevector_call_stack:
            import traceback
            self.init_call_stack = traceback.format_stack()

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        if not isinstance(value, six.string_types):
            raise PyrtlError('WireVector names must be strings')
        self._block.wirevector_by_name.pop(self._name, None)
        self._name = value
        self._block.add_wirevector(self)

    def __hash__(self):
        return id(self)

    def __str__(self):
        """ A string representation of the wire in 'name/bitwidth code'  form """
        return ''.join([self.name, '/', str(self.bitwidth), self._code])

    def _validate_bitwidth(self, bitwidth):
        if bitwidth is not None:
            if not isinstance(bitwidth, numbers.Integral):
                raise PyrtlError('bitwidth must be from type int or unspecified, instead "%s"'
                                 ' was passed of type %s' % (str(bitwidth), type(bitwidth)))
            elif bitwidth <= 0:
                raise PyrtlError('you are trying a negative bitwidth? awesome but wrong')
        self.bitwidth = bitwidth

    def _build(self, other):
        # Actually create and add wirevector to logic block
        # This might be called immediately from ilshift, or delayed from conditional assignment
        net = LogicNet(
            op='w',
            op_param=None,
            args=(other,),
            dests=(self,))
        working_block().add_net(net)

    def _prepare_for_assignment(self, rhs):
        # Convert right-hand-side to wires and propagate bitwidth if necessary
        from .helperfuncs import as_wires
        rhs = as_wires(rhs, bitwidth=self.bitwidth)
        if self.bitwidth is None:
            self.bitwidth = rhs.bitwidth
        return rhs

    def __ilshift__(self, other):
        """ Wire assignment operator (assign other to self). """
        other = self._prepare_for_assignment(other)
        self._build(other)
        return self

    def __ior__(self, other):
        """ Conditional assignment operator (only valid under Conditional Update). """
        from .conditional import _build
        if not self.bitwidth:
            raise PyrtlError('Conditional assignment only defined on '
                             'WireVectors with pre-defined bitwidths')
        other = self._prepare_for_assignment(other)
        _build(self, other)
        return self

    def logicop(self, other, op):
        from .helperfuncs import as_wires, match_bitwidth

        a, b = self, other
        # convert constants if necessary
        b = as_wires(b)

        # check size of operands
        a, b = match_bitwidth(a, b)
        resultlen = len(a)  # both are the same length now

        # some operations actually create more or less bits
        if op in ['+', '-']:
            resultlen += 1  # extra bit required for carry
        elif op in ['*']:
            resultlen = resultlen * 2  # more bits needed for mult
        elif op in ['<', '>', '=']:
            resultlen = 1

        s = WireVector(bitwidth=resultlen)
        net = LogicNet(
            op=op,
            op_param=None,
            args=(a, b),
            dests=(s,))
        working_block().add_net(net)
        return s

    def __bool__(self):
        """ Use of a wirevector in a statement like "a or b" is forbidden."""
        # python provides no way to overload these logical operations, and thus they
        # are very much not likely to be doing the thing that the programmer would be
        # expecting.
        raise PyrtlError('cannot covert wirevector to compile-time boolean.  This error '
                         'often happens when you attempt to use WireVectors with "==" or '
                         'something that calls "__eq__", such as when you test if a '
                         'wirevector is "in" something')

    __nonzero__ = __bool__  # for Python 2 and 3 compatibility

    def __and__(self, other):
        """ Creates a LogicNet that ands two wires together into a single wire
            :return Wirevector: the result wire of the operation
        """
        return self.logicop(other, '&')

    def __rand__(self, other):
        return self.logicop(other, '&')

    def __iand__(self, other):
        raise PyrtlError('error, operation not allowed on WireVectors')

    def __or__(self, other):
        """ Creates a LogicNet that ors two wires together into a single wire
            :return Wirevector: the result wire of the operation
        """
        return self.logicop(other, '|')

    def __ror__(self, other):
        return self.logicop(other, '|')

    # __ior__ used for conditional assignment above

    def __xor__(self, other):
        """ Creates a LogicNet that xors two wires together into a single wire
            :return Wirevector: the result wire of the operation
        """
        return self.logicop(other, '^')

    def __rxor__(self, other):
        return self.logicop(other, '^')

    def __ixor__(self, other):
        raise PyrtlError('error, operation not allowed on WireVectors')

    def __add__(self, other):
        """
        Creates a LogicNet that adds two wires together into a single wire
        :return Wirevector: the result wire of the operation
          The resulting wire has one more bit than the longer of the two input wires
        Addition is compatible with two's complement signed numbers
        """
        return self.logicop(other, '+')

    def __radd__(self, other):
        return self.logicop(other, '+')

    def __iadd__(self, other):
        raise PyrtlError('error, operation not allowed on WireVectors')

    def __sub__(self, other):
        """
        Creates a LogicNet that subtracts the right wire from the left one
        :return Wirevector: the result wire of the operation
          The resulting wire has one more bit than the longer of the two input wires
        Subtraction is compatible with two's complement signed numbers
        """
        return self.logicop(other, '-')

    def __rsub__(self, other):
        from .helperfuncs import as_wires
        other = as_wires(other)  # '-' op is not symmetric
        return other.logicop(self, '-')

    def __isub__(self, other):
        raise PyrtlError('error, operation not allowed on WireVectors')

    def __mul__(self, other):
        """
        Creates a LogicNet that multiplies two different wirevectors
        :return Wirevector: the result wire of the operation
          The resulting wire's bitwidth is the sum of the two input wires' bitwidths
        Subtraction is compatible with two's complement signed numbers
        """
        return self.logicop(other, '*')

    def __rmul__(self, other):
        return self.logicop(other, '*')

    def __imul__(self, other):
        raise PyrtlError('error, operation not allowed on WireVectors')

    def __lt__(self, other):
        """
        Creates a LogicNet that calculates whether a wire is less than another
        :return Wirevector: a one bit result wire of the operation
        """
        return self.logicop(other, '<')

    def __le__(self, other):
        """
        Creates LogicNets that calculates whether a wire is less than or equal to another
        :return Wirevector: a one bit result wire of the operation
        """
        return ~ self.logicop(other, '>')

    def __eq__(self, other):
        """
        Creates a LogicNet that calculates whether a wire is equal to another
        :return Wirevector: a one bit result wire of the operation
        """
        return self.logicop(other, '=')

    def __ne__(self, other):
        """
        Creates LogicNets that calculates whether a wire not equal to another
        :return Wirevector: a one bit result wire of the operation
        """
        return ~ self.logicop(other, '=')

    def __gt__(self, other):
        """
        Creates a LogicNet that calculates whether a wire is greater than another
        :return Wirevector: a one bit result wire of the operation
        """
        return self.logicop(other, '>')

    def __ge__(self, other):
        """
        Creates LogicNets that calculates whether a wire is greater than or equal to another
        :return Wirevector: a one bit result wire of the operation
        """
        return ~ self.logicop(other, '<')

    def __invert__(self):
        """
        Creates LogicNets that inverts a wire
        :return Wirevector: a result wire for the operation
        """
        outwire = WireVector(bitwidth=len(self))
        net = LogicNet(
            op='~',
            op_param=None,
            args=(self,),
            dests=(outwire,))
        working_block().add_net(net)
        return outwire

    def __getitem__(self, item):
        """
        Grabs a subset of the wires
        :return Wirevector: a result wire for the operation
        """
        if self.bitwidth is None:
            raise PyrtlError('You cannot get a subset of a wire with no bitwidth')
        allindex = range(self.bitwidth)
        if isinstance(item, int):
            selectednums = (allindex[item], )  # this method handles negative numbers correctly
        else:  # slice
            selectednums = tuple(allindex[item])
        if not selectednums:
            raise PyrtlError('selection %s must have at least select one wire' % str(item))
        outwire = WireVector(bitwidth=len(selectednums))
        net = LogicNet(
            op='s',
            op_param=selectednums,
            args=(self,),
            dests=(outwire,))
        working_block().add_net(net)
        return outwire

    def __lshift__(self, other):
        raise PyrtlError("Shifting using the << and >> operators are not supported"
                         "in PyRTL."
                         "Instead if you are trying to select bits in a wire, use"
                         "the indexing operator (wire[indexes]) instead.\n\n"
                         "For example: wire[2:9] selects the wires from index 2 to "
                         "index 8 to make a new length 7 wire.")

    __rshift__ = __lshift__

    def __mod__(self, other):
        raise PyrtlError("Masking with the % operator is not supported"
                         "in PyRTL. "
                         "Instead if you are trying to select bits in a wire, use"
                         "the indexing operator (wire[indexes]) instead.\n\n"
                         "For example: wire[2:9] selects the wires from index 2 to "
                         "index 8 to make a new length 7 wire.")

    def __len__(self):
        if self.bitwidth is None:
            raise PyrtlError('length of wirevector not yet defined')
        else:
            return self.bitwidth

    def __enter__(self):
        """ use wires as contexts for conditional assignments. """
        from .conditional import _push_condition
        _push_condition(self)

    def __exit__(self, *execinfo):
        from .conditional import _pop_condition
        _pop_condition()

    # more functions for wires
    def nand(self, other):
        """ Creates a LogicNet that nands two wires together into a single wire
            :return Wirevector: the result wire of the operation
        """
        return self.logicop(other, 'n')

    @property
    def bitmask(self):
        """ Return an integer appropriate as a bitmask for this wirevector. """
        if "_bitmask" not in self.__dict__:
            self._bitmask = (1 << len(self)) - 1
        return self._bitmask

    def sign_extended(self, bitwidth):
        """ Return a sign extended wirevector derived from self """
        return self._extend_with_bit(bitwidth, self[-1])

    def zero_extended(self, bitwidth):
        """ Return a zero extended wirevector derived from self """
        return self._extend_with_bit(bitwidth, 0)

    def _extend_with_bit(self, bitwidth, extbit):
        numext = bitwidth - self.bitwidth
        if numext == 0:
            return self
        elif numext < 0:
            raise PyrtlError(
                'Neither zero_extended nor sign_extended can'
                ' reduce the number of bits')
        else:
            from .helperfuncs import concat
            if isinstance(extbit, int):
                extbit = Const(0, bitwidth=1)
            extvector = WireVector(bitwidth=numext)
            net = LogicNet(
                op='s',
                op_param=(0,)*numext,
                args=(extbit,),
                dests=(extvector,))
            working_block().add_net(net)
            return concat(extvector, self)


# -----------------------------------------------------------------------
#  ___     ___  ___       __   ___  __           ___  __  ___  __   __   __
# |__  \_/  |  |__  |\ | |  \ |__  |  \    \  / |__  /  `  |  /  \ |__) /__`
# |___ / \  |  |___ | \| |__/ |___ |__/     \/  |___ \__,  |  \__/ |  \ .__/
#

class Input(WireVector):
    """ A WireVector type denoting inputs to a block (no writers) """
    _code = 'I'

    def __init__(self, bitwidth=None, name=None, block=None):
        super(Input, self).__init__(bitwidth=bitwidth, name=name, block=block)

    def __ilshift__(self, _):
        """ This is an illegal op for Inputs. They cannot be assigned to in this way """
        raise PyrtlError(
            'Connection using <<= operator attempted on Input. '
            'Inputs, such as "%s", cannot have values generated internally. '
            "aka they can't have other wires driving it"
            % str(self.name))

    def __ior__(self, _):
        """ This is an illegal op for Inputs. They cannot be assigned to in this way """
        raise PyrtlError(
            'Connection using |= operator attempted on Input. '
            'Inputs, such as "%s", cannot have values generated internally. '
            "aka they can't have other wires driving it"
            % str(self.name))


class Output(WireVector):
    """ A WireVector type denoting outputs of a block (no readers)
    Even though Output seems to have valid ops such as __or__ , using
    them will throw an error.
    """
    _code = 'O'

    def __init__(self, bitwidth=None, name=None, block=None):
        super(Output, self).__init__(bitwidth, name, block)


class Const(WireVector):
    """ A WireVector representation of a constant value

    Converts from bool, integer, or verilog-style strings to a constant
    of the specified bitwidth.  If the bitwidth is too short to represent
    the specified constant then an error is raised.  If a possitive
    integer is specified the bitwidth can be infered from the constant.
    If a negative integer is provided in the simulation, it is converted
    to a two's complement representation of the specified bitwidth."""

    _code = 'C'

    def __init__(self, val, bitwidth=None, block=None):
        """ Construct a constant implementation at initialization

        :param int or str val: The value for the const wirevector
        :return: a wirevector object representing a const wire

        Descriptions for all parameters not listed above can be found at
        py:method:: WireVector.__init__()
        """
        self._validate_bitwidth(bitwidth)
        num, bitwidth = _gen_val_and_bitwidth(val, bitwidth)

        if num < 0:
            raise PyrtlInternalError(
                'Const somehow evaluating to negative integer after checks')
        if (num >> bitwidth) != 0:
            raise PyrtlError(
                'error constant "%s" cannot fit in the specified %d bits'
                % (str(num), bitwidth))

        name = next_constvar_name(num)

        super(Const, self).__init__(bitwidth=bitwidth, name=name, block=block)
        # add the member "val" to track the value of the constant
        self.val = num

    def __ilshift__(self, other):
        """ This is an illegal op for Consts. Their value is set in the __init__ function"""
        raise PyrtlError(
            'ConstWires, such as "%s", should never be assigned to with <<='
            % str(self.name))

    def __ior__(self, _):
        """ This is an illegal op for Inputs. They cannot be assigned to in this way """
        raise PyrtlError(
            'Connection using |= operator attempted on Const. '
            'ConstWires, such as "%s", cannot have values generated internally. '
            "aka they cannot have other wires driving it"
            % str(self.name))


def _gen_val_and_bitwidth(val, bitwidth=None):
    if isinstance(val, bool):
        return _convert_bool(val, bitwidth)
    elif isinstance(val, numbers.Integral):
        return _validate_const_int(val, bitwidth)
    elif isinstance(val, six.string_types):
        return _convert_verilog_str(val, bitwidth)
    else:
        raise PyrtlError('error, the value of Const is of an improper type, "%s"'
                         'proper types are bool, int, and string' % type(val))


def _convert_bool(bool_val, bitwidth=None):
    num = int(bool_val)
    if bitwidth is None:
        bitwidth = 1
    if bitwidth != 1:
        raise PyrtlError('error, boolean has bitwidth not equal to 1')
    return num, bitwidth


def _validate_const_int(val, bitwidth=None):
    if val >= 0:
        num = val
        # infer bitwidth if it is not specified explicitly
        if bitwidth is None:
            bitwidth = len(bin(num)) - 2  # the -2 for the "0b" at the start of the string
    else:  # val is negative
        if bitwidth is None:
            raise PyrtlError(
                'negative Const values must have bitwidth declared explicitly')
        if (val >> bitwidth-1) != -1:
            raise PyrtlError('insufficient bits for negative number')
        num = val & ((1 << bitwidth) - 1)  # result is a twos complement value
    return num, bitwidth


def _convert_verilog_str(val, bitwidth=None):
    bases = {'b': 2, 'o': 8, 'd': 10, 'h': 16, 'x': 16}
    if bitwidth is not None:
        raise PyrtlError('error, bitwidth parameter of const should be'
                         ' unspecified when the const is created from a string'
                         ' (instead use verilog style specification)')
    neg = False
    if val.startswith('-'):
        neg = True
        val = val[1:]
    split_string = val.lower().split("'")
    if len(split_string) != 2:
        raise PyrtlError('error, string for Const not in verilog style format')
    try:
        bitwidth = int(split_string[0])
        sval = split_string[1]
        if sval[0] == 's':
            raise PyrtlError('signed integers are not supported in verilog-style Const')
        base = 10
        if sval[0] in bases:
            base = bases[sval[0]]
            sval = sval[1:]
        sval = sval.replace('_', '')
        num = int(sval, base)
    except (IndexError, ValueError):
        raise PyrtlError('error, string for Const not in verilog style format')
    if neg and num:
        if (num >> bitwidth-1):
            raise PyrtlError('insufficient bits for negative number')
        num = (1 << bitwidth) - num
    return num, bitwidth


class Register(WireVector):
    """ A WireVector with a register state element embedded.

    Registers only update their outputs on posedge of an implicit
    clk signal.  The "value" in the current cycle can be accessed
    by just referencing the Register itself.  To set the value for
    the next cycle (after the next posedge) you write to the
    property .next with the <<= operator.  For example, if you want
    to specify a counter it would look like: "a.next <<= a + 1"
    """
    _code = 'R'

    # When the register is called as such:  r.next <<= foo
    # the sequence of actions that happens is:
    # 1) The property .next is called to get the "value" of r.next
    # 2) The "value" is then passed to __ilshift__
    #
    # The resulting behavior should enforce the following:
    # r.next <<= 5  -- good
    # a <<= r       -- good
    # r <<= 5       -- error
    # a <<= r.next  -- error
    # r.next = 5    -- error

    class _Next(object):
        """ This is the type returned by "r.next". """

        def __init__(self, reg):
            self.reg = reg

        def __ilshift__(self, other):
            return self.reg._next_ilshift(other)

        def __ior__(self, other):
            return self.reg._next_ior(other)

        def __bool__(self):
            """ Use of a _next in a statement like "a or b" is forbidden."""
            raise PyrtlError('cannot covert Register.next to compile-time boolean.  This error '
                             'often happens when you attempt to use a Register.next with "==" or '
                             'something that calls "__eq__", such as when you test if a '
                             'Register.next is "in" something')

        __nonzero__ = __bool__  # for Python 2 and 3 compatibility

    class _NextSetter(object):
        """ This is the type returned by __ilshift__ which r.next will be assigned. """

        def __init__(self, rhs, is_conditional):
            self.rhs = rhs
            self.is_conditional = is_conditional

    def __init__(self, bitwidth, name=None, block=None):
        super(Register, self).__init__(bitwidth=bitwidth, name=name, block=block)
        self.reg_in = None  # wire vector setting self.next

    @property
    def next(self):
        """
        This property is the way to set what the wirevector will be the next
        cycle (aka, it is before the D-Latch)
        """
        return Register._Next(self)

    def __ilshift__(self, other):
        raise PyrtlError('error, you cannot set registers directly, net .next instead')

    def __ior__(self, other):
        raise PyrtlError('error, you cannot set registers directly, net .next instead')

    def _next_ilshift(self, other):
        from .helperfuncs import as_wires
        other = as_wires(other, bitwidth=self.bitwidth)
        if self.bitwidth is None:
            self.bitwidth = other.bitwidth
        return Register._NextSetter(other, is_conditional=False)

    def _next_ior(self, other):
        from .helperfuncs import as_wires
        other = as_wires(other, bitwidth=self.bitwidth)
        if not self.bitwidth:
            raise PyrtlError('Conditional assignment only defined on '
                             'Registers with pre-defined bitwidths')
        return Register._NextSetter(other, is_conditional=True)

    @next.setter
    def next(self, nextsetter):
        from .conditional import _build
        if not isinstance(nextsetter, Register._NextSetter):
            raise PyrtlError('error, .next should be set with "<<=" or "|=" operators')
        elif self.reg_in is not None:
            raise PyrtlError('error, .next value should be set once and only once')
        elif nextsetter.is_conditional:
            _build(self, nextsetter.rhs)
        else:
            self._build(nextsetter.rhs)

    def _build(self, next):
        # this actually builds the register which might be from directly setting
        # the property "next" or delayed when there is a conditional assignement
        self.reg_in = next
        net = LogicNet('r', None, args=(self.reg_in,), dests=(self,))
        working_block().add_net(net)
