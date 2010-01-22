"""The definition of a KBUS Message (and its subclasses).

On Ubuntu, if I want ordinary users (in the admin group) to be able to
read/write '/dev/kbus0' then I need to have a file
'/etc/udev/rules.d/45-kbus.rules' which contains::

    KERNEL=="kbus[0-9]*",  MODE="0666", GROUP="admin"

Other operating systems will have other mechanisms, and on an embedded system
it is likely enough not to do this, as the "user" will be root.
"""

# ***** BEGIN LICENSE BLOCK *****
# Version: MPL 1.1
#
# The contents of this file are subject to the Mozilla Public License Version
# 1.1 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
# for the specific language governing rights and limitations under the
# License.
#
# The Original Code is the KBUS Lightweight Linux-kernel mediated
# message system
#
# The Initial Developer of the Original Code is Kynesim, Cambridge UK.
# Portions created by the Initial Developer are Copyright (C) 2009
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
#   Kynesim, Cambridge UK
#   Tibs <tony.ibbs@gmail.com>
#
# ***** END LICENSE BLOCK *****

from __future__ import with_statement
import ctypes
import array
import string


def _BIT(nr):
    return 1L << nr

def _set_bit(value, which):
    """Return 'value' with the bit 'which' set.

    'which' should be something like _BIT(3).
    """
    return value | which

def _clear_bit(value, which):
    """Return 'value' with the bit 'which' cleared.

    'which' should be something like _BIT(3).
    """
    if value & which:
        mask = ~which
        value = value & mask
    return value

class MessageId(ctypes.Structure):
    """A wrapper around a message id.

        >>> a = MessageId(1, 2)
        >>> a
        MessageId(1, 2)
        >>> a < MessageId(2, 2) and a < MessageId(1, 3)
        True
        >>> a == MessageId(1, 2)
        True
        >>> a > MessageId(0, 2) and a > MessageId(1, 1)
        True

    We support addition in a limited manner:

        >>> a + 3
        MessageId(1, 5)

    simply to make it convenient to generate unique message ids. This returns
    a new MessageId - it doesn't amend the existing one.
    """
    _fields_ = [('network_id', ctypes.c_uint32),
                ('serial_num', ctypes.c_uint32)]

    def __repr__(self):
        return 'MessageId(%u, %u)'%(self.network_id, self.serial_num)

    def _short_str(self):
        """For use in message structure reporting
        """
        return '%u:%u'%(self.network_id, self.serial_num)

    def __str__(self):
        return '[%u:%u]'%(self.network_id, self.serial_num)

    def __cmp__(self, other):
        if not isinstance(other, MessageId):
            return NotImplemented
        if self.network_id == other.network_id:
            if self.serial_num == other.serial_num:
                return 0
            elif self.serial_num < other.serial_num:
                return -1
            else:
                return 1
        elif self.network_id < other.network_id:
            return -1
        else:
            return 1

    def __add__(self, other):
        if not isinstance(other, int):
            return NotImplemented
        else:
            return MessageId(self.network_id, self.serial_num+other)

def _same_message_struct(this, that):
    """Returns true if the two message structures are the same.

    Copes with both "plain" and "entire" messages (i.e., those
    which are a _MessageHeaderStruct with pointers to name and data,
    and also those which are an 'EntireMessageStruct', with the
    name and (any) data concatenated after the header).
    """
    if not isinstance(this, _MessageHeaderStruct) and \
       not isinstance(this, _EntireMessageStructBaseclass):
        return False

    if not isinstance(that, _MessageHeaderStruct) and \
       not isinstance(that, _EntireMessageStructBaseclass):
        return False

    if (this.id != that.id or
        this.in_reply_to != that.in_reply_to or
        this.to != that.to or
        this.from_ != that.from_ or
        this.flags != that.flags or
        this.name_len != that.name_len or
        this.data_len != that.data_len or
        this.name != that.name):
        return False

    if this.data_len:
        this_data = c_data_as_string(this.is_pointy, this.data, this.data_len)
        that_data = c_data_as_string(this.is_pointy, that.data, that.data_len)
        return this_data == that_data
    return True

def _equivalent_message_struct(this, that):
    """Returns true if the two messages are mostly the same.

    For purposes of this comparison, we ignore:

    * 'id',
    * 'flags',
    * 'in_reply_to' and
    * 'from'

    Copes with both "plain" and "entire" messages (i.e., those
    which are a _MessageHeaderStruct with pointers to name and data,
    and also those which are an 'EntireMessageStruct', with the
    name and (any) data concatenated after the header).
    """
    if not isinstance(this, _MessageHeaderStruct) and \
       not isinstance(this, _EntireMessageStructBaseclass):
        return False

    if not isinstance(that, _MessageHeaderStruct) and \
       not isinstance(that, _EntireMessageStructBaseclass):
        return False

    if (this.to != that.to or
        this.name_len != that.name_len or
        this.data_len != that.data_len or
        this.name != that.name):
        return False

    if this.data_len:
        this_data = c_data_as_string(this.is_pointy, this.data, this.data_len)
        that_data = c_data_as_string(this.is_pointy, that.data, that.data_len)
        return this_data == that_data
    return True

    #if this.data_len:
    #    if isinstance(this.data, int):
    #        this_array = ctypes.cast(this.data, ctypes.POINTER(ctypes.c_uint8))
    #    else:
    #        this_array = this.data
    #    if isinstance(that.data, int):
    #        that_array = ctypes.cast(that.data, ctypes.POINTER(ctypes.c_uint8))
    #    else:
    #        that_array = that.data
    #
    #    for ii in range(this.data_len):
    #        if this_array[ii] != that_array[ii]:
    #            return False
    #return True

def c_data_as_string(is_pointy, data, data_len):
    """Return the message data as a string.
    """
    # And, somewhat inefficiently, convert it to a (byte) string
    w = []
    for ii in range(data_len):
        w.append(chr(data[ii]))
    return ''.join(w)

def hexdata(data):
    r"""Return a representation of a 'string' in printable form.

    Doesn't use whitespace or anything not in letters, digits or punctuation.
    Thus, the resultant string should be entirely equivalent in "meaning" to
    the input.

    For instance:

        >>> hexdata('1234')
        '1234'
        >>> hexdata('')
        ''
        >>> hexdata(' ')
        '\\x20'
        >>> hexdata('\x27')
        "'"
        >>> hexdata('\x03')
        '\\x03'
    """
    pretty = string.letters + string.digits + string.punctuation
    words = []
    for ch in data:
        if ch in pretty:
            words.append(ch)
        else:
            words.append('\\x%02x'%ord(ch))
    return ''.join(words)

def hexify(data):
    r"""Return a representation of a 'string' as hex values.

    For instance:

        >>> hexify('1234')
        '31 32 33 34'
        >>> hexify('')
        ''
        >>> hexify('\x27')
        '27'
    """
    words = []
    for ch in data:
        words.append('%02x'%ord(ch))
    return ' '.join(words)

def _int_tuple_as_str(data):
    """Return a representation of a tuple of integers, as a string.
    """
    words = []
    for w in data:
        words.append('0x%x'%w)

    if len(words) == 0:
        return '()'
    elif len(words) == 1:
        return '(%s,)'%words[0]
    else:
        return '(%s)'%(', '.join(words))

class _MessageHeaderStruct(ctypes.Structure):
    """The datastructure for a Message header.

    A "plain" message is represented as a Message header with pointers
    to its name and (any) data.
    """
    _fields_ = [('start_guard', ctypes.c_uint32),
                ('id',          MessageId),
                ('in_reply_to', MessageId),
                ('to',          ctypes.c_uint32),
                ('from_',       ctypes.c_uint32), # named consistently with elsewhere
                ('flags',       ctypes.c_uint32),
                ('name_len',    ctypes.c_uint32),
                ('data_len',    ctypes.c_uint32),
                ('name',        ctypes.c_char_p),
                ('data',        ctypes.POINTER(ctypes.c_uint8)),
                ('end_guard',   ctypes.c_uint32)]

    is_pointy = True

    def __repr__(self):
        """For debugging, not construction of an instance of ourselves.
        """
        if self.name == None:
            nn = 'None'
        else:
            nn = repr(hexdata(self.name))
        if self.data == None:
            dd = 'None'
        else:
            # We need to retrieve our array from the pointer - ick
            array = ctypes.cast(self.data, ctypes.POINTER(ctypes.c_uint8))
            # And, somewhat inefficiently, convert it to something printable
            w = []
            for ii in range(self.data_len):
                w.append(chr(array[ii]))
            s = ''.join(w)
            dd = repr(hexdata(s))
        return "<%08x] %s %s %u %u %08x %u %u %s %s [%08x>"%(
                self.start_guard,
                self.id._short_str(),
                self.in_reply_to._short_str(),
                self.to,
                self.from_,
                self.flags,
                self.name_len,
                self.data_len,
                nn,
                dd,
                self.end_guard)

    def __eq__(self, other):
        return _same_message_struct(self, other)

    def __ne__(self, other):
        return not _same_message_struct(self, other)

    def equivalent(self, other):
        """Returns true if the two messages are mostly the same.

        For purposes of this comparison, we ignore:

        * 'id',
        * 'flags',
        * 'in_reply_to' and
        * 'from'

        Copes with both "plain" and "entire" messages (i.e., those
        which are a _MessageHeaderStruct with pointers to name and data,
        and also those which are an 'EntireMessageStruct', with the
        name and (any) data concatenated after the header).
        """
        return _equivalent_message_struct(self, other)

def _struct_to_string(struct):
    return ctypes.string_at(ctypes.addressof(struct), ctypes.sizeof(struct))

def _struct_from_string(struct_class, data):
    thing = struct_class()
    ctypes.memmove(ctypes.addressof(thing), data, ctypes.sizeof(thing))
    return thing

def message_from_parts(id, in_reply_to, to, from_, flags, name, data):
    """Return a new Message header structure, with name and data attached.

    - 'id' and 'in_reply_to' are (network_id, serial_num) tuples
    - 'to', 'in_reply_to' and 'from_' are 0 or a KSock id
    - 'name' is a string
    - 'data' is a string or None
    """
    name_len = len(name)

    if data:
        data_len = len(data)
    else:
        data_len = 0

    # C wants us to have a terminating 0 byte
    name += '\0'
    # And we want to pad the result out to a multiple of 4 bytes
    # ...this is about the nastiest way possible of doing it...
    while len(name)%4:
        name += '\0'

    padded_name_len = len(name)

    # We want to pad the data out in the same manner
    # (but without the terminating 0 byte)
    if data:
        while len(data)%4:
            data += '\0'
        padded_data_len = len(data)
    else:
        padded_data_len = 0

    name_ptr = ctypes.c_char_p(name)
    if data:
        # This seems a bit clumsy and wasteful, but I can't see
        # how else to do it
        DataArray = ctypes.c_uint8 * padded_data_len
        data_ptr = DataArray( *[ord(x) for x in data] )
    else:
        data_ptr = None

    return _MessageHeaderStruct(Message.START_GUARD,
                                id, in_reply_to,
                                to, from_, flags, name_len, data_len,
                                name_ptr, data_ptr, Message.END_GUARD)

def message_from_string(msg_data):
    """Return a "pointy" message structure from the given data.

    'data' is a string-like object (as, for instance, returned by 'read')
    """
    h = _struct_from_string(_MessageHeaderStruct, msg_data)

    # Don't forget that the string will be terminated with a 0 byte
    padded_name_len = 4*((h.name_len +1 + 3) / 4)

    # But not so the data
    padded_data_len = 4*((h.data_len + 3) / 4)

    h.name = msg_data[52:52+h.name_len]

    data_offset = 52+padded_name_len

    if h.data_len == 0:
        h.data = None
    else:
        data = msg_data[data_offset:data_offset+h.data_len]

        DataArray = ctypes.c_uint8 * h.data_len
        h.data = DataArray( *[ord(x) for x in data] )

    final_end_guard = msg_data[data_offset+padded_data_len:]
    return h

class _EntireMessageStructBaseclass(ctypes.Structure):
    """The baseclass for our "entire" message structure.

    Defined separately just to reduce the amount of code executed in the
    functions that *build* the classes.

    It is required that the fields defined be 'header', 'rest_name',
    'rest_data' and 'rest_end_guard' -- but since I'm assuming this will only
    be (directly) used internally to kbus.py, I'm happy with that.

        (Specifically, see the ``_specific_entire_message_struct`` function)
    """

    def __repr__(self):
        """For debugging, not construction of an instance of ourselves.
        """
        if self.name_len:
            name_repr = repr(hexdata(self.rest_name[:self.name_len]))
        else:
            name_repr = 'None'
        if self.data_len:
            data_repr = repr(hexdata(self.rest_data[:self.data_len]))
        else:
            data_repr = None
        return "%s %s %s [%08x>"%(
                self.header,
                name_repr,
                data_repr,
                self.rest_end_guard)

    # If we didn't have the problem of trying to look for the
    # message name and data in the "rest" of the structure, we
    # could use the "anonymous" capability to make the "header"
    # names be used directly. But that would not allow us to
    # fudge "name" and "data", so...

    is_pointy = False

    @property
    def start_guard(self):
        return self.header.start_guard

    @property
    def id(self):
        return self.header.id

    # Announcement wants to be able to overwrite in_reply_to
    def get_in_reply_to(self):
        return self.header.in_reply_to

    def set_in_reply_to(self, value):
        self.header.in_reply_to = value

    in_reply_to = property(get_in_reply_to, set_in_reply_to)

    @property
    def to(self):
        return self.header.to

    @property
    def from_(self):
        return self.header.from_

    # It's useful to be able to set flags
    def get_flags(self):
        return self.header.flags

    def set_flags(self, value):
        self.header.flags = value

    flags = property(get_flags, set_flags)

    @property
    def name_len(self):
        return self.header.name_len

    @property
    def data_len(self):
        return self.header.data_len

    @property
    def end_guard(self):
        return self.header.end_guard

    @property
    def name(self):
        name_len = self.header.name_len
        return self.rest_name[:name_len]

    @property
    def data(self):
        data_len = self.header.data_len
        if data_len:
            return self.rest_data[:data_len]
        else:
            return None

    def __eq__(self, other):
        return _same_message_struct(self, other)

    def __ne__(self, other):
        return not _same_message_struct(self, other)

    def equivalent(self, other):
        return _equivalent_message_struct(self, other)

# Is this premature optimisation?
# I don't think Python would cache the different classes for me,
# and it seems wasteful to create a new class for *every* message,
# given there will be a lot of messages that are very similar...
_specific_entire_message_struct_dict = {}

def _specific_entire_message_struct(padded_name_len, padded_data_len):
    """Return a specific subclass of _MessageHeaderStruct
    """
    key = (padded_name_len, padded_data_len)
    if key in _specific_entire_message_struct_dict:
        return _specific_entire_message_struct_dict[key]
    else:
        class localEntireMessageStruct(_EntireMessageStructBaseclass):
            _fields_ = [('header',     _MessageHeaderStruct),
                        ('rest_name',  ctypes.c_char  * padded_name_len),
                        ('rest_data',  ctypes.c_uint8 * padded_data_len),
                        #('rest_data',  ctypes.c_char * padded_data_len),
                        ('rest_end_guard',  ctypes.c_uint32)]
        _specific_entire_message_struct_dict[key] = localEntireMessageStruct
        return localEntireMessageStruct

def entire_message_from_parts(id, in_reply_to, to, from_, flags, name, data):
    """Return a new message structure of the correct shape.

    - 'id' and 'in_reply_to' are None or (network_id, serial_num) tuples
    - 'to', 'in_reply_to' and 'from_' are 0 or a KSock id
    - 'name' is a string
    - 'data' is a string or None
    """

    if id is None:
        id = MessageId(0,0)

    if in_reply_to is None:
        in_reply_to = MessageId(0,0)

    name_len = len(name)

    if data is None:
        data = ''

    data_len = len(data)

    # C wants us to have a terminating 0 byte
    name += '\0'
    # And we want to pad the result out to a multiple of 4 bytes
    # ...this is about the nastiest way possible of doing it...
    while len(name)%4:
        name += '\0'

    padded_name_len = len(name)

    # We want to pad the data out in the same manner
    # (but without the terminating 0 byte)
    while len(data)%4:
        data += '\0'
    padded_data_len = len(data)

    header = _MessageHeaderStruct(Message.START_GUARD,
                                  id, in_reply_to,
                                  to, from_, flags, name_len, data_len,
                                  None, None, Message.END_GUARD)

    DataArray = ctypes.c_uint8 * padded_data_len
    data_array = DataArray( *[ord(x) for x in data] )

    # We rather rely on 'data' "disappearing" (being of zero length)
    # if 'data_len' is zero, and it appears that that just works.

    local_class = _specific_entire_message_struct(padded_name_len,
                                                  padded_data_len)

    return local_class(header, name, data_array, Message.END_GUARD)

def entire_message_from_string(data):
    """Return a message structure of a size that satisfies.

    'data' is a string-like object (as, for instance, returned by 'read')
    """
    ## ===================================
    debug = False
    if debug:
        print
        print 'entire_message_from_string(%d:%s)'%(len(data),hexify(data))
    ## ===================================
    h = _struct_from_string(_MessageHeaderStruct, data)
    ## ===================================
    if debug:
        print '_MessageHeaderStruct: %s'%h
    ## ===================================

    # Don't forget that the string will be terminated with a 0 byte
    padded_name_len = 4*((h.name_len +1 + 3) / 4)

    # But not so the data
    padded_data_len = 4*((h.data_len + 3) / 4)

    local_class = _specific_entire_message_struct(padded_name_len,
                                                  padded_data_len)

    ## ===================================
    if debug:
        print 'name_len %d -> %d, data_len %d -> %d'%(h.name_len, padded_name_len, h.data_len, padded_data_len)
        x = _struct_from_string(local_class, data)
        print '_specific_class:      %s'%x
        print
    ## ===================================

    return _struct_from_string(local_class, data)

class Message(object):
    """A wrapper for a KBUS message

    A Message can be created in a variety of ways. Perhaps most obviously:

        >>> msg = Message('$.Fred')
        >>> msg
        Message('$.Fred', data=None, to=0L, from_=0L, in_reply_to=None, flags=0x00000000, id=None)

        >>> msg = Message('$.Fred', '1234')
        >>> msg
        Message('$.Fred', data='1234', to=0L, from_=0L, in_reply_to=None, flags=0x00000000, id=None)

        >>> msg = Message('$.Fred', '12345678')
        >>> msg
        Message('$.Fred', data='12345678', to=0L, from_=0L, in_reply_to=None, flags=0x00000000, id=None)

        >>> msg1 = Message('$.Fred', data='1234')
        >>> msg1
        Message('$.Fred', data='1234', to=0L, from_=0L, in_reply_to=None, flags=0x00000000, id=None)

    A Message can be constructed from another message directly:

        >>> msg2 = Message(msg1)
        >>> msg2 == msg1
        True

    or from the '.extract()' tuple:

        >>> msg3 = Message(msg1.extract())
        >>> msg3 == msg1
        True

    or from an equivalent list::

        >>> msg3 = Message(list(msg1.extract()))
        >>> msg3 == msg1
        True

    or one can use a "string" -- for instance, as returned by the KSock 'read'
    method:

        >>> msg_as_string = msg1.to_string()
        >>> msg4 = Message(msg_as_string)
        >>> msg4 == msg1
        True

    When constructing a message from another message, one may override
    particular values (but not the name):

        >>> msg5 = Message(msg1, to=9, in_reply_to=MessageId(0, 3))
        >>> msg5
        Message('$.Fred', data='1234', to=9L, from_=0L, in_reply_to=MessageId(0, 3), flags=0x00000000, id=None)

        >>> msg5a = Message(msg1, to=9, in_reply_to=MessageId(0, 3))
        >>> msg5a == msg5
        True

    However, whilst it is possible to set (for instance) 'to' back to 0 by this method:

        >>> msg6 = Message(msg5, to=0)
        >>> msg6
        Message('$.Fred', data='1234', to=0L, from_=0L, in_reply_to=MessageId(0, 3), flags=0x00000000, id=None)

    (and the same for any of the integer fields), it is not possible to set any
    of the message id fields to None:

        >>> msg6 = Message(msg5, in_reply_to=None)
        >>> msg6
        Message('$.Fred', data='1234', to=9L, from_=0L, in_reply_to=MessageId(0, 3), flags=0x00000000, id=None)

    If you need to do that, go via the 'extract()' method:

        >>> (id, in_reply_to, to, from_, flags, name, data) = msg5.extract()
        >>> msg6 = Message(name, data, to, from_, None, flags, id)
        >>> msg6
        Message('$.Fred', data='1234', to=9L, from_=0L, in_reply_to=None, flags=0x00000000, id=None)

    For convenience, the parts of a Message may be retrieved as properties:

        >>> print msg1.id
        None
        >>> msg1.name
        '$.Fred'
        >>> msg1.to
        0L
        >>> msg1.from_
        0L
        >>> print msg1.in_reply_to
        None
        >>> msg1.flags
        0L
        >>> msg1.data
        '1234'

    Message ids are objects if set:

        >>> msg1 = Message('$.Fred', data='1234', id=MessageId(0, 33))
        >>> msg1
        Message('$.Fred', data='1234', to=0L, from_=0L, in_reply_to=None, flags=0x00000000, id=MessageId(0, 33))
        >>> msg1.id
        MessageId(0, 33)

    The arguments to Message() are:

    - 'arg' -- this is the initial argument, and is a message name (a string
      that starts '$.'), a Message, or a string representing an "entire"
      message.

    If 'arg' is a message name, or another Message then the keyword arguments
    may be used (for another Message, they override the values in that Message).
    if 'arg' is a message-as-a-string, they will be ignored):

    - 'data' is data for the Message, either None or a Python string.
    - 'to' is the KSock id for the destination, for use in replies or in
      stateful messaging. Normally it should be left 0.
    - 'from_' is the KSock id of the sender. Normally this should be left
      0, as it is assigned by KBUS.
    - if 'in_reply_to' is non-zero, then it is the KSock id to which the
      reply shall go (taken from the 'from_' field in the original message).
      Setting 'in_reply_to' non-zero indicates that the Message *is* a reply.
      See also the Reply class, and especially the 'reply_to' function, which
      makes constructing replies simpler.
    - 'flags' can be used to set the flags for the message. If all that is
      wanted is to set Messages.WANT_A_REPLY flag, it is simpler to use the
      Request class to construct the message.
    - 'id' may be used to set the message id, although unless the network_id is
      set, KBUS will ignore this and set the id internally (this can be useful
      when constructing a message to compare received messages against).

    Our internal values are:

    - 'msg', which is the actual message datastructure
    """

    START_GUARD = 0x7375626B
    END_GUARD   = 0x6B627573

    WANT_A_REPLY        = _BIT(0)
    WANT_YOU_TO_REPLY   = _BIT(1)
    SYNTHETIC           = _BIT(2)
    URGENT              = _BIT(3)

    ALL_OR_WAIT         = _BIT(8)
    ALL_OR_FAIL         = _BIT(9)

    def __init__(self, arg, data=None, to=None, from_=None, in_reply_to=None, flags=None, id=None):
        """Initialise a Message.

        All named arguments are meant to be "unset" by default.
        """

        if isinstance(arg, Message):
            self._merge_args(arg.extract(), data, to, from_, in_reply_to, flags, id)
        elif isinstance(arg, tuple) or isinstance(arg, list):
            # A tuple from .extract(), or an equivalent tuple/list
            if len(arg) != 7:
                raise ValueError("Tuple arg to Message() must have"
                        " 7 values, not %d"%len(arg))
            else:
                self._merge_args(arg, data, to, from_, in_reply_to, flags, id)
        elif isinstance(arg, str):
            if arg.startswith('$.'):
                # It looks like a message name
                name = arg
                self._from_data(name, data, to, from_, in_reply_to, flags, id)
            elif data is None and to is None and from_ is None and \
                    in_reply_to is None and flags is None and id is None:
                # Assume it's sensible data...
                self.msg = entire_message_from_string(arg)
            else:
                raise ValueError('If message data is given as a string,'
                                 ' no other arguments are allowed')
        else:
            raise ValueError('Argument %s does not seem to make sense'%repr(arg))

        # Make sure the result *looks* like a message
        self._check()

    def _merge_args(self, extracted, this_data, this_to, this_from_,
                    this_in_reply_to, this_flags, this_id):
        """Set our data from a msg.extract() tuple and optional arguments.

        Note that, if given, 'id' and 'in_reply_to' must be MessageId
        instances.

        Note that 'data' must be:

        1. a string, or something else compatible.
        2. None.
        """
        (id, in_reply_to, to, from_, flags, name, data) = extracted
        if this_data        is not None: data        = this_data
        if this_to          is not None: to          = this_to
        if this_from_       is not None: from_       = this_from_
        if this_in_reply_to is not None: in_reply_to = this_in_reply_to
        if this_flags       is not None: flags       = this_flags
        if this_id          is not None: id          = this_id
        self._from_data(name, data, to, from_, in_reply_to, flags, id)

    def _from_data(self, name, data, to, from_, in_reply_to, flags, id):
        """Set our data from individual arguments.

        Note that, if given, 'id' and 'in_reply_to' must be MessageId
        instances.
        """

        if id:
            id_tuple = (id.network_id, id.serial_num)
        else:
            id_tuple = (0, 0)

        if in_reply_to:
            in_reply_to_tuple = (in_reply_to.network_id, in_reply_to.serial_num)
        else:
            in_reply_to_tuple = (0, 0)

        if not to:
            to = 0

        if not from_:
            from_ = 0

        if not flags:
            flags = 0

        self.msg = message_from_parts(id_tuple, in_reply_to_tuple,
                                      to, from_, flags, name, data)

    def _check(self):
        """Perform some basic sanity checks on our data.
        """
        # XXX Make the reporting of problems nicer for the user!
        assert self.msg.start_guard == self.START_GUARD
        assert self.msg.end_guard == self.END_GUARD
        if self.msg.name_len < 3:
            raise ValueError("Message name is %d long, minimum is 3"
                             " (e.g., '$.*')"%self.msg.name_len)

    def __repr__(self):
        (id, in_reply_to, to, from_, flags, name, data) = self.extract()
        if data is None:
            data_repr = 'None'
        else:
            data_repr = repr(hexdata(data))
        args = [repr(name),
                'data=%s'%data_repr,
                'to='+repr(to),
                'from_='+repr(from_),
                'in_reply_to='+repr(in_reply_to),
                'flags=0x%08x'%flags,
                'id='+repr(id)]
        return 'Message(%s)'%(', '.join(args))

    def __str__(self):
        (id, in_reply_to, to, from_, flags, name, data) = self.extract()
        # Try to be a bit friendly about what type of message this is
        if in_reply_to:
            if name.startswith('$.KBUS.'):
                what = 'Status'
            else:
                what = 'Reply'
        elif flags & Message.WANT_A_REPLY:
            what = 'Request'
        else:
            what = 'Announcement'
        parts = [repr(name)]
        if id:
            parts.append('id=%s'%str(id))
        if to:
            parts.append('to=%d'%to)
        if from_:
            parts.append('from=%d'%from_)
        if in_reply_to:
            parts.append('in_reply_to=%s'%str(in_reply_to))
        if flags:
            txt = self._flag_text(flags)
            if txt:
                parts.append('flags=0x%x (%s)'%(flags,txt))
            else:
                parts.append('flags=0x%x'%flags)
        if data:
            parts.append('data=%s'%repr(data))
        return '<%s %s>'%(what, ', '.join(parts))

    def _flag_text(self, flags):
        """A simple representation of the known flags.
        """
        words = []
        if flags & Message.WANT_A_REPLY:
            words.append('REQ')
        if flags & Message.WANT_YOU_TO_REPLY:
            words.append('YOU')
        if flags & Message.SYNTHETIC:
            words.append('SYN')
        if flags & Message.URGENT:
            words.append('URG')
        if len(words):
            return ','.join(words)
        else:
            return ''

    def __eq__(self, other):
        if not isinstance(other, Message):
            return False
        else:
            return (self.msg == other.msg)

    def __ne__(self, other):
        if not isinstance(other, Message):
            return True
        else:
            return (self.msg != other.msg)

    def total_length(self):
        """Return the total length of this message.

        A Message may be held in one of two ways:

        * "pointy" - this is a message header, with references to the
          message name and data.
        * "entire" - this is a message header with the message name
          and data (and an extra end guard) appended to it.

        Message construction may produce either of these (although
        construction of a message from a string will always produce
        an "entire" message). Reading a message from a KSock returns
        an "entire" message string.

        The actual "pointy" or "entire" message data is held in the
        'msg' value of the Message instance.

        The 'to_string()' method returns the data for an "entire" message.

        This function calculates the length of the equivalent "entire"
        message for this Message.
        """
        # And we're going to do it the slow and wasteful way
        #
        # XXX Just calculate this, instead of copying stuff...
        return len(self.to_string())

    def equivalent(self, other):
        """Returns true if the two messages are mostly the same.

        For purposes of this comparison, we ignore:

        * 'id',
        * 'flags',
        * 'in_reply_to' and
        * 'from'
        """
        return self.msg.equivalent(other.msg)
        #return _equivalent_message_struct(self, other)

    def set_want_reply(self, value=True):
        """Set or unset the 'we want a reply' flag.
        """
        if value:
            self.msg.flags = _set_bit(self.msg.flags, Message.WANT_A_REPLY)
        else:
            self.msg.flags = _clear_bit(self.msg.flags, Message.WANT_A_REPLY)

    def set_urgent(self, value=True):
        """Set or unset the 'urgent message' flag.
        """
        if value:
            self.msg.flags = _set_bit(self.msg.flags, Message.URGENT)
        else:
            self.msg.flags = _clear_bit(self.msg.flags, Message.URGENT)

    def wants_us_to_reply(self):
        """Return true if we (*specifically* us) are should reply to this message.
        """
        return self.msg.flags & Message.WANT_YOU_TO_REPLY

    def is_synthetic(self):
        """Return true if this is a synthetic message - one generated by KBUS.
        """
        return self.msg.flags & Message.SYNTHETIC

    def is_urgent(self):
        """Return true if this is an urgent message.
        """
        return self.msg.flags & Message.URGENT

    @property
    def id(self):
        network_id = self.msg.id.network_id
        serial_num = self.msg.id.serial_num
        if network_id == 0 and serial_num == 0:
            return None
        else:
            #return MessageId(network_id, serial_num)
            return self.msg.id

    @property
    def in_reply_to(self):
        network_id = self.msg.in_reply_to.network_id
        serial_num = self.msg.in_reply_to.serial_num
        if network_id == 0 and serial_num == 0:
            return None
        else:
            #return MessageId(network_id, serial_num)
            return self.msg.in_reply_to

    @property
    def to(self):
        return self.msg.to

    @property
    def from_(self):
        return self.msg.from_

    @property
    def flags(self):
        return self.msg.flags

    @property
    def name(self):
        name_len = self.msg.name_len
        # Make sure we remove the padding bytes (although they *should* be
        # '\0', and so "reasonably safe")
        return self.msg.name[:name_len]

    @property
    def data(self):
        if self.msg.data_len == 0:
            return None
        # To be friendly, return data as a Python (byte) string
        return c_data_as_string(self.msg.is_pointy, self.msg.data, self.msg.data_len)

    def extract(self):
        """Return our parts as a tuple.

        The values are returned in something approximating the order
        within the message itself:

            (id, in_reply_to, to, from_, flags, name, data)

        This is not the same order as the keyword arguments to Message().
        """
        return (self.id, self.in_reply_to, self.to, self.from_,
                self.flags, self.name, self.data)

    def to_string(self):
        """Return the message as a string.

        This returns the entirety of the message as a Python string.

        In order to do this, it first coerces the mesage to an "entire"
        message (so that we don't have any dangling "pointers" to the
        name or data).
        """
        (id, in_reply_to, to, from_, flags, name, data) = self.extract()
        tmp = entire_message_from_parts(id, in_reply_to, to, from_, flags,
                                        name, data)
        return _struct_to_string(tmp)

    def cast(self):
        """Return (a copy of) ourselves as an appropriate subclass of Message

        Reading from a KSock returns a Message, whatever the actual message
        type. Normally, this is OK, but sometimes it would be nice to have
        an actual message of the correct class.
        """
        # If it has in_reply_to set...
        if self.in_reply_to:
            # Status messages have a specific sort of name
            if self.msg.name.startswith('$.KBUS.'):
                return Status(self)
            else:
                return Reply(self)

        # If it has the WANT_A_REPLY flag set, then it's a Request
        if self.msg.flags & Message.WANT_A_REPLY:
            return Request(self)

        # Otherwise, it's basically an Announcement (at least, that's a good bet)
        return Announcement(self)

class Announcement(Message):
    """A "plain" message, needing no reply

    This is intended to be a convenient way of constructing a message that
    is just aimed at any listeners.

    It's also a terminological convenience - all of the "message" things are
    clearly messages, so we need a special name for "plain" messages...
    There's an argument for just factory functions to create these things,
    but a class feels a little cleaner to me.

    An Announcement can be created in a variety of ways. Perhaps most obviously:

        >>> ann1 = Announcement('$.Fred', data='1234')
        >>> ann1
        Announcement('$.Fred', data='1234', to=0L, from_=0L, flags=0x00000000, id=None)

    Since Announcement is a "plain" Message, we expect to be able to use the
    normal ways of instantiating a Message for an Announcement.

    So, an Announcement can be constructed from another message directly:

        >>> ann2 = Announcement(ann1)
        >>> ann2 == ann1
        True

        >>> msg = Announcement(ann1)
        >>> ann2a = Announcement(msg)
        >>> ann2 == ann2a
        True

    Since it's an Announcement, there's no 'in_reply_to' argument

        >>> fail = Announcement('$.Fred', in_reply_to=None)
        Traceback (most recent call last):
        ...
        TypeError: __init__() got an unexpected keyword argument 'in_reply_to'

    and the 'in_reply_to' value in Message objects is ignored:

        >>> msg = Message('$.Fred', data='1234', in_reply_to=MessageId(1, 2))
        >>> ann = Announcement(msg)
        >>> ann
        Announcement('$.Fred', data='1234', to=0L, from_=0L, flags=0x00000000, id=None)
        >>> print ann.in_reply_to
        None

    or from the '.extract()' tuple - again, 'reply_to' will be ignored:

        >>> ann3 = Announcement(ann1.extract())
        >>> ann3 == ann1
        True

    or from an equivalent list (and as above for 'reply_to'):

        >>> ann3 = Announcement(list(ann1.extract()))
        >>> ann3 == ann1
        True

    Or one can the same thing represented as a string:

        >>> ann_as_string = ann1.to_string()
        >>> ann4 = Announcement(ann_as_string)
        >>> ann4 == ann1
        True

    For convenience, the parts of an Announcement may be retrieved as properties:

        >>> print ann1.id
        None
        >>> ann1.name
        '$.Fred'
        >>> ann1.to
        0L
        >>> ann1.from_
        0L
        >>> print ann1.in_reply_to # always expected to be None
        None
        >>> ann1.flags
        0L
        >>> ann1.data
        '1234'

    Note that:

    1. An Announcement message is such because it is not a message of another
       type. There is nothing else special about it.
    """

    # I would quite like to do::
    #
    #   def __init__(self, arg, **kwargs):
    #
    # and then::
    #
    #   super(Announcement, self).__init__(arg, **kwargs)
    #
    # but then I wouldn't be able to do::
    #
    #   r = Announcement('$.Fred', 'data')
    #
    # which I *can* do (and want to be able to do) with Message

    def __init__(self, arg, data=None, to=None, from_=None, flags=None, id=None):
        """Arguments are the same as for Message itself, absent 'in_reply_to'.
        """
        # Just do what the caller asked for directly
        super(Announcement, self).__init__(arg, data=data, to=to,
                                           from_=from_, flags=flags, id=id)
        # And, in case 'in_reply_to' got set by that
        self.msg.in_reply_to = MessageId(0, 0)

    def set_want_reply(self, value=True):
        """Announcements are not Requests.
        """
        raise TypeError("Announcements are not Requests")

    def __repr__(self):
        (id, in_reply_to, to, from_, flags, name, data) = self.extract()
        if data is None:
            data_repr = 'None'
        else:
            data_repr = repr(hexdata(data))
        args = [repr(name),
                'data=%s'%data_repr,
                'to='+repr(to),
                'from_='+repr(from_),
                'flags=0x%08x'%flags,
                'id='+repr(id)]
        return 'Announcement(%s)'%(', '.join(args))

class Request(Message):
    """A message that wants a reply.

    This is intended to be a convenient way of constructing a message that
    wants a reply.

    It doesn't take an 'in_reply_to' initialisation argument:

        >>> fail = Request('$.Fred', in_reply_to=None)
        Traceback (most recent call last):
        ...
        TypeError: __init__() got an unexpected keyword argument 'in_reply_to'

    And it automatically sets the 'wants a reply' flag, but otherwise it
    behaves just like a Message.

    For instance, consider:

        >>> msg = Message('$.Fred', data='1234', flags=Message.WANT_A_REPLY)
        >>> msg
        Message('$.Fred', data='1234', to=0L, from_=0L, in_reply_to=None, flags=0x00000001, id=None)
        >>> req = Request('$.Fred', data='1234')
        >>> req
        Request('$.Fred', data='1234', to=0L, from_=0L, flags=0x00000001, id=None)
        >>> req == msg
        True

    Note that:

    1. A request message is a request just because it has the
       Message.WANT_A_REPLY flag set. There is nothing else special about it.
    """

    # I would quite like to do::
    #
    #   def __init__(self, arg, **kwargs):
    #
    # and then::
    #
    #   super(Request, self).__init__(arg, **kwargs)
    #
    # but then I wouldn't be able to do::
    #
    #   r = Request('$.Fred', 'data')
    #
    # which I *can* do (and want to be able to do) with Message

    def __init__(self, arg, data=None, to=None, from_=None, flags=None, id=None):
        """Arguments are exactly the same as for Message itself.
        """
        # First, just do what the caller asked for directly
        # but with 'in_reply_to' as 0
        super(Request, self).__init__(arg, data, to, from_, 0, flags, id)
        # But then make sure that the "wants a reply" flag is set
        super(Request, self).set_want_reply(True)

    def __repr__(self):
        (id, in_reply_to, to, from_, flags, name, data) = self.extract()
        if data is None:
            data_repr = 'None'
        else:
            data_repr = repr(hexdata(data))
        args = [repr(name),
                'data=%s'%data_repr,
                'to='+repr(to),
                'from_='+repr(from_),
                'flags=0x%08x'%flags,
                'id='+repr(id)]
        return 'Request(%s)'%(', '.join(args))

    def set_want_reply(self):
        raise TypeError('Request always has "want a reply" set')

class Reply(Message):
    """A reply message.

        (Note that the constructor for this class does *not* flip fields (such
        as 'id' and 'in_reply_to', or 'from_' and 'to') when building the Reply
        - if you want that behaviour (and you probably do), use the "reply_to"
        function.)

    Thus Reply can be used as, for instance:

        >>> direct = Reply('$.Fred', to=27, in_reply_to=MessageId(0, 132))
        >>> direct
        Reply('$.Fred', data=None, to=27L, from_=0L, in_reply_to=MessageId(0, 132), flags=0x00000000, id=None)
        >>> reply = Reply(direct)
        >>> direct == reply
        True

    Since a Reply is a Message with its 'in_reply_to' set, this *must* be provided:

        >>> msg = Message('$.Fred', data='1234', from_=27, to=99, id=MessageId(0, 132), flags=Message.WANT_A_REPLY)
        >>> msg
        Message('$.Fred', data='1234', to=99L, from_=27L, in_reply_to=None, flags=0x00000001, id=MessageId(0, 132))
        >>> reply = Reply(msg)
        Traceback (most recent call last):
        ...
        ValueError: A Reply must specify in_reply_to

        >>> reply = Reply(msg, in_reply_to=MessageId(0, 5))
        >>> reply
        Reply('$.Fred', data='1234', to=99L, from_=27L, in_reply_to=MessageId(0, 5), flags=0x00000001, id=MessageId(0, 132))

    It's also possible to construct a Reply in most of the other ways a Message
    can be constructed. For instance:

        >>> rep2 = Reply(direct.to_string())
        >>> rep2 == direct
        True
        >>> rep4 = Reply(direct.extract())
        >>> rep4 == direct
        True
    """

    def __init__(self, arg, data=None, to=None, from_=None, in_reply_to=None, flags=None, id=None):
        """Just do what the user asked, but they must give 'in_reply_to'.
        """
        
        super(Reply, self).__init__(arg, data=data, to=to, from_=from_,
                                   in_reply_to=in_reply_to, flags=flags, id=id)
        if self.in_reply_to is None:
            raise ValueError("A Reply must specify in_reply_to")

    def __repr__(self):
        (id, in_reply_to, to, from_, flags, name, data) = self.extract()
        if data is None:
            data_repr = 'None'
        else:
            data_repr = repr(hexdata(data))
        args = [repr(name),
                'data=%s'%data_repr,
                'to='+repr(to),
                'from_='+repr(from_),
                'in_reply_to='+repr(in_reply_to),
                'flags=0x%08x'%flags,
                'id='+repr(id)]
        return 'Reply(%s)'%(', '.join(args))

class Status(Message):
    """A status message, from KBUS.

    This is provided as a sugar-coating around the messages KBUS sends us. As
    such, it is not expected that a normal user would want to construct one,
    and the initialisation mechanisms are correspondingly more restrictive.

    For instance:

        >>> msg = Message('$.KBUS.Dummy', from_=27, to=99, in_reply_to=MessageId(0, 132))
        >>> msg
        Message('$.KBUS.Dummy', data=None, to=99L, from_=27L, in_reply_to=MessageId(0, 132), flags=0x00000000, id=None)
        >>> status = Status(msg.to_string())
        >>> status
        Status('$.KBUS.Dummy', data=None, to=99L, from_=27L, in_reply_to=MessageId(0, 132), flags=0x00000000, id=None)

    Note that:

    1. A status message is such because it is a (sort of) Reply, with the
       message name starting with '$.KBUS.'.
    """

    def __init__(self, original):
        # Actually, this is slightly more forgiving than the docstring
        # suggests, but conversely I'm not going to hold the user's hand
        # if they do something that's not supported...
        super(Status, self).__init__(original)

    def __repr__(self):
        (id, in_reply_to, to, from_, flags, name, data) = self.extract()
        if data is None:
            data_repr = 'None'
        else:
            data_repr = repr(hexdata(data))
        args = [repr(name),
                'data=%s'%data_repr,
                'to='+repr(to),
                'from_='+repr(from_),
                'in_reply_to='+repr(in_reply_to),
                'flags=0x%08x'%flags,
                'id='+repr(id)]
        return 'Status(%s)'%(', '.join(args))

def reply_to(original, data=None, flags=0):
    """Return a Reply to the given Message.

    This is intended to be the normal way of constructing a reply message.

    For instance:

        >>> msg = Message('$.Fred', data='1234', from_=27, to=99, id=MessageId(0, 132), flags=Message.WANT_A_REPLY|Message.WANT_YOU_TO_REPLY)
        >>> msg
        Message('$.Fred', data='1234', to=99L, from_=27L, in_reply_to=None, flags=0x00000003, id=MessageId(0, 132))
        >>> reply = reply_to(msg)
        >>> reply
        Reply('$.Fred', data=None, to=27L, from_=0L, in_reply_to=MessageId(0, 132), flags=0x00000000, id=None)

    Note that:

    1. The message we're constructing a reply to must be a message that wants
       a reply. Specifically, this means that it must have the "WANT_A_REPLY"
       flag set, and also the "WANT_YOU_TO_REPLY" flag. This last is because
       anyone listening to a Request will "see" the "WANT_A_REPLY" flag, but
       only the (single) replier will receive the message with the
       "WANT_YOU_TO_REPLY" flag set.
    2. A reply message is a reply because it has the 'in_reply_to' field set.
       This indicates the message id of the original message, the one we're
       replying to.
    3. As normal, the Reply's own message id is unset - KBUS will set this, as
       for any message.
    4. We give a specific 'to' value, the id of the KSock that sent the
       original message, and thus the 'from' value in the original message.
    5. We keep the same message name, but don't copy the original message's
       data. If we want to send data in a reply message, it will be our own
       data.

    The other arguments available are 'flags' (allowing the setting of flags
    such as Message.ALL_OR_WAIT, for instance), and 'data', allowing reply data
    to be added:

        >>> rep4 = reply_to(msg, flags=Message.ALL_OR_WAIT, data='1234')
        >>> rep4
        Reply('$.Fred', data='1234', to=27L, from_=0L, in_reply_to=MessageId(0, 132), flags=0x00000100, id=None)
    """

    # Check we're allowed to reply to this
    if original.flags & (Message.WANT_A_REPLY | Message.WANT_YOU_TO_REPLY) != \
            Message.WANT_A_REPLY | Message.WANT_YOU_TO_REPLY:
        raise ValueError("Cannot form a reply to a message that does not have"
                " WANT_A_REPLY and WANT_YOU_TO_REPLY set: %s"%original)

    (id, in_reply_to, to, from_, original_flags, name, data_tuple) = original.extract()
    # We reply to the original sender (to), indicating which message we're
    # responding to (in_reply_to).
    #
    # The fact that in_reply_to is set means that we *are* a reply.
    #
    # We don't need to set any flags. We definitely *don't* want to copy
    # any flags from the original message.
    return Reply(name, data=data, in_reply_to=id, to=from_, flags=flags)




class _ReplierBindEventHeader(ctypes.Structure):
    """The "header" part of a '$.KBUS.ReplierBindEvent' message
    """
    _fields_ = [('is_bind', ctypes.c_uint32),
                ('binder',  ctypes.c_uint32),
                ('name_len',ctypes.c_uint32)]

def split_replier_bind_event_data(data):
    """Split the data from a '$.KBUS.ReplierBindEvent' message.

    Returns a tuple of the form (is_bind, binder, name)
    """

    hdr = _struct_from_string(_ReplierBindEventHeader, data)

    name = data[12:12+hdr.name_len]

    return (hdr.is_bind, hdr.binder, name)

# vim: set tabstop=8 shiftwidth=4 expandtab:
