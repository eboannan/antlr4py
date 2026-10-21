"""Construct and serialize ANTLR v4 automata using the Python runtime types.

The version-4 wire format follows ANTLR's ATNSerializer/ATNDeserializer.
Copyright (c) 2012-2017 The ANTLR Project. All rights reserved.
Use of this file is governed by the repository's BSD-3-Clause license.
"""
from antlr4.IntervalSet import IntervalSet
from antlr4.Token import Token
from antlr4.LL1Analyzer import LL1Analyzer
from antlr4.PredictionContext import PredictionContext
from antlr4.atn.ATN import ATN
from antlr4.atn.ATNDeserializer import ATNDeserializer, SERIALIZED_VERSION
from antlr4.atn.ATNState import (
    BasicState, RuleStartState, RuleStopState, BlockStartState, BlockEndState,
    BasicBlockStartState, DecisionState, TokensStartState, StarLoopEntryState,
    StarBlockStartState, StarLoopbackState, PlusBlockStartState,
    PlusLoopbackState, LoopEndState,
)
from antlr4.atn.ATNType import ATNType
from antlr4.atn.LexerAction import LexerSkipAction, LexerActionType
from antlr4.atn.LexerAction import (
    LexerMoreAction, LexerPopModeAction, LexerPushModeAction, LexerModeAction,
    LexerTypeAction, LexerChannelAction, LexerCustomAction,
)
from .characters import character_set, negated_set, case_set
from .naming import escaped
from antlr4.atn.Transition import (
    Transition, EpsilonTransition, AtomTransition, RuleTransition,
    SetTransition, ActionTransition, PrecedencePredicateTransition, NotSetTransition,
    RangeTransition, WildcardTransition, PredicateTransition,
)


def serialize_atn(atn):
    """Serialize runtime ATN objects to version-4 integer data.

    Rule-stop return edges are derived by the deserializer, not written. Set
    intervals use inclusive bounds on the wire and exclusive bounds in Python.
    """
    data = [SERIALIZED_VERSION, int(atn.grammarType), atn.maxTokenType, len(atn.states)]
    nongreedy, precedence, sets, edges = [], [], {}, []
    for state in atn.states:
        if state is None:
            data.append(0)
            continue
        data.extend((state.stateType, state.ruleIndex))
        if isinstance(state, LoopEndState):
            data.append(state.loopBackState.stateNumber)
        elif isinstance(state, BlockStartState):
            data.append(state.endState.stateNumber)
        if isinstance(state, DecisionState) and state.nonGreedy:
            nongreedy.append(state.stateNumber)
        if isinstance(state, RuleStartState) and state.isPrecedenceRule:
            precedence.append(state.stateNumber)
        if isinstance(state, RuleStopState):
            continue
        for edge in state.transitions:
            target, kind = edge.target.stateNumber, edge.serializationType
            a = b = c = 0
            if kind == Transition.RULE:
                target = edge.followState.stateNumber
                a, b, c = edge.target.stateNumber, edge.ruleIndex, edge.precedence
            elif kind == Transition.ATOM:
                a = edge.label_
                if a == Token.EOF:
                    a, c = 0, 1
            elif kind == Transition.RANGE:
                a, b = edge.start, edge.stop
                if a == Token.EOF:
                    a, c = 0, 1
            elif kind in (Transition.SET, Transition.NOT_SET):
                key = tuple((r.start, r.stop) for r in edge.label.intervals or ())
                if key not in sets:
                    sets[key] = len(sets)
                a = sets[key]
            elif kind == Transition.ACTION:
                a, b, c = edge.ruleIndex, edge.actionIndex, int(edge.isCtxDependent)
            elif kind == Transition.PREDICATE:
                a, b, c = edge.ruleIndex, edge.predIndex, int(edge.isCtxDependent)
            elif kind == Transition.PRECEDENCE:
                a = edge.precedence
            elif kind not in (Transition.EPSILON, Transition.WILDCARD):
                raise ValueError(f'Unsupported transition type: {kind}')
            edges.append((state.stateNumber, target, kind, a, b, c))
    data.extend((len(nongreedy), *nongreedy, len(precedence), *precedence))
    data.append(len(atn.ruleToStartState))
    for index, start in enumerate(atn.ruleToStartState):
        data.append(start.stateNumber)
        if atn.grammarType == ATNType.LEXER:
            data.append(atn.ruleToTokenType[index])
    data.extend((len(atn.modeToStartState), *(s.stateNumber for s in atn.modeToStartState)))
    data.append(len(sets))
    for intervals in sets:
        has_eof = any(start <= Token.EOF < stop for start, stop in intervals)
        positive = [(max(0, start), stop-1) for start, stop in intervals if stop > 0]
        data.extend((len(positive), int(has_eof)))
        for interval in positive:
            data.extend(interval)
    data.append(len(edges))
    for edge in edges:
        data.extend(edge)
    data.extend((len(atn.decisionToState), *(s.stateNumber for s in atn.decisionToState)))
    if atn.grammarType == ATNType.LEXER:
        actions = atn.lexerActions or []
        data.append(len(actions))
        for action in actions:
            kind = action.actionType
            a = b = 0
            if kind == LexerActionType.CHANNEL:
                a = action.channel
            elif kind in (LexerActionType.MODE, LexerActionType.PUSH_MODE):
                a = action.mode
            elif kind == LexerActionType.TYPE:
                a = action.type
            elif kind == LexerActionType.CUSTOM:
                a, b = action.ruleIndex, action.actionIndex
            elif kind not in (LexerActionType.MORE, LexerActionType.POP_MODE, LexerActionType.SKIP):
                raise ValueError(f'Unsupported lexer action type: {kind}')
            data.extend((int(kind), a, b))
    return data


class ATNBuilder:
    def case_values(self, values, rule):
        definition = self.grammar.lexer[rule]
        enabled = definition.case_insensitive
        if enabled is None:
            enabled = self.grammar.options.get('caseInsensitive') == 'true'
        return case_set(values) if enabled else values

    def token_set(self, node):
        kind, value = node
        if kind == 'seq' and len(value) == 1:
            return self.token_set(value[0])
        if kind == 'alt':
            children = [self.token_set(child) for child in value]
            if all(child is not None for child in children):
                return set().union(*children)
        if kind == 'lit':
            return {self.grammar.literals[value]}
        if kind == 'ref' and value not in self.grammar.rules:
            return {Token.EOF if value == 'EOF' else self.grammar.tokens[value]}
        return None

    def __init__(self, grammar, lexer=False, annotations=None):
        self.grammar = grammar
        self.lexer = lexer
        self.annotations = annotations if annotations is not None else {}
        max_type = max([0, *grammar.tokens.values(), *grammar.literals.values()])
        self.atn = ATN(ATNType.LEXER if lexer else ATNType.PARSER, max_type)
        self.atn.ruleToStopState = []
        self.atn.lexerActions = [] if lexer else None
        self.rule_indices = ({r.name: i for i, r in enumerate(grammar.lexer)} if lexer else
                             {name: i for i, name in enumerate(grammar.rules)})

    def state(self, cls, rule):
        state = cls()
        state.ruleIndex = rule
        self.atn.addState(state)
        return state

    @staticmethod
    def epsilon(source, target):
        source.addTransition(EpsilonTransition(target))

    def block(self, cls, rule):
        start, end = self.state(cls, rule), self.state(BlockEndState, rule)
        start.endState, end.startState = end, start
        return start, end

    def build(self):
        rules = ([r.node for r in self.grammar.lexer] if self.lexer
                 else list(self.grammar.rules.values()))
        if self.lexer:
            for name in self.grammar.modes:
                mode = self.state(TokensStartState, -1)
                self.atn.modeToStartState.append(mode)
                self.atn.modeNameToStartState[name] = mode
                self.atn.defineDecisionState(mode)
            self.atn.ruleToTokenType = [r.token_type for r in self.grammar.lexer]
        for rule in range(len(rules)):
            start = self.state(RuleStartState, rule)
            if not self.lexer:
                start.isPrecedenceRule = list(self.grammar.rules)[rule] in self.grammar.left_recursive
            stop = self.state(RuleStopState, rule)
            start.stopState = stop
            self.atn.ruleToStartState.append(start)
            self.atn.ruleToStopState.append(stop)
        for rule, node in enumerate(rules):
            start, stop = self.atn.ruleToStartState[rule], self.atn.ruleToStopState[rule]
            entry = self.state(BasicState, rule)
            self.epsilon(start, entry)
            if self.lexer:
                definition = self.grammar.lexer[rule]
                if not definition.fragment:
                    self.epsilon(self.atn.modeNameToStartState[definition.mode], start)
            end = stop
            self.expression(node, entry, end, rule)
        # Deserialization both verifies structural invariants and supplies the
        # rule-return edges omitted from the wire format.
        data = serialize_atn(self.atn)
        return ATNDeserializer().deserialize(data)

    def expression(self, node, source, target, rule):
        kind, value = node
        if kind in ('label', 'altlabel'):
            entry, end = self.state(BasicState, rule), self.state(BasicState, rule)
            self.epsilon(source, entry)
            self.epsilon(end, target)
            if kind == 'altlabel':
                name, child = value
                self.annotations.setdefault(entry.stateNumber, []).append(('select', name))
            else:
                name, many, child = value
                from .annotations import element
                unwrapped = element(child)
                child_kind = unwrapped[0]
                reference = unwrapped[1][0] if child_kind in ('invoke', 'call') else unwrapped[1]
                is_rule = child_kind in ('invoke', 'call') or child_kind == 'ref' and reference in self.grammar.rules
                if not self.lexer and not many and not is_rule and (child_kind == 'not' or child_kind not in ('ref', 'lit') and self.token_set(child) is not None):
                    self.annotations.setdefault(entry.stateNumber, []).append(('capture', escaped(name)))
                self.annotations.setdefault(end.stateNumber, []).append(('bind', escaped(name), many, is_rule))
            self.expression(child, entry, end, rule)
        elif kind == 'leftbind':
            self.annotations.setdefault(source.stateNumber, []).append(('left', escaped(value[0]), value[1]))
            self.epsilon(source, target)
        elif kind == 'enter':
            self.annotations.setdefault(source.stateNumber, []).append(('enter',))
            self.epsilon(source, target)
        elif kind == 'invoke':
            self.annotations.setdefault(source.stateNumber, []).append(('arguments', value[1]))
            self.expression(('ref', value[0]), source, target, rule)
        elif kind == 'seq':
            for index, child in enumerate(value):
                end = target if index == len(value)-1 else self.state(BasicState, rule)
                self.expression(child, source, end, rule)
                source = end
            if not value:
                self.epsilon(source, target)
        elif kind == 'lit' and self.lexer:
            for index, char in enumerate(value):
                end = target if index == len(value)-1 else self.state(BasicState, rule)
                values = IntervalSet()
                values.addOne(ord(char))
                values = self.case_values(values, rule)
                if len(values) == 1:
                    source.addTransition(AtomTransition(end, ord(char)))
                else:
                    source.addTransition(SetTransition(end, values))
                source = end
        elif kind == 'set':
            source.addTransition(SetTransition(target, self.case_values(character_set(value), rule)))
        elif kind == 'range':
            values = IntervalSet()
            values.addRange(range(value[0], value[1]+1))
            mapped = self.case_values(values, rule)
            if mapped.intervals == values.intervals:
                source.addTransition(RangeTransition(target, *value))
            else:
                source.addTransition(SetTransition(target, mapped))
        elif kind == 'not':
            if self.lexer:
                excluded = self.case_values(negated_set(value), rule)
            else:
                excluded = IntervalSet()
                for token in sorted(self.token_set(value)):
                    excluded.addOne(token)
            source.addTransition(NotSetTransition(target, excluded))
        elif kind == 'wildcard':
            source.addTransition(WildcardTransition(target))
        elif kind == 'commands':
            body, commands = value
            end = self.state(BasicState, rule)
            self.expression(body, source, end, rule)
            for index, (command, argument) in enumerate(commands):
                following = target if index == len(commands)-1 else self.state(BasicState, rule)
                action = self.lexer_action(command, argument)
                if action not in self.atn.lexerActions:
                    self.atn.lexerActions.append(action)
                end.addTransition(ActionTransition(following, rule, self.atn.lexerActions.index(action), False))
                end = following
        elif kind == 'prec':
            source.addTransition(PrecedencePredicateTransition(target, value))
        elif kind == 'predicate':
            source.addTransition(PredicateTransition(target, rule, value['index'], value['dependent']))
        elif kind == 'action':
            index = value['index']
            if self.lexer:
                self.atn.lexerActions.append(LexerCustomAction(rule, index))
                index = len(self.atn.lexerActions)-1
            source.addTransition(ActionTransition(target, rule, index, value['dependent']))
        elif kind == 'call' or (kind == 'ref' and value in self.rule_indices):
            name, precedence = value if kind == 'call' else (value, 0)
            index = self.rule_indices[name]
            source.addTransition(RuleTransition(self.atn.ruleToStartState[index], index, precedence, target))
        elif kind in ('lit', 'ref'):
            token = (self.grammar.literals[value] if kind == 'lit' else
                     Token.EOF if value == 'EOF' else self.grammar.tokens[value])
            source.addTransition(AtomTransition(target, token))
        elif kind == 'alt' and not self.lexer and self.token_set(node) is not None:
            tokens = IntervalSet()
            for token in sorted(self.token_set(node)):
                tokens.addOne(token)
            source.addTransition(SetTransition(target, tokens))
        elif kind in ('alt', '?', '??'):
            start, end = self.block(BasicBlockStartState, rule)
            self.epsilon(source, start)
            self.epsilon(end, target)
            children = value if kind == 'alt' else [value, ('seq', [])]
            if kind == '?' and not self.lexer:
                self.annotations.setdefault(start.stateNumber, []).append(('optional', 2))
            if kind == '??':
                children.reverse()
                start.nonGreedy = True
            for child in children:
                # Keep the empty alternative directly connected to the block
                # end, as expected by the runtime's optional-block prediction.
                if child == ('seq', []):
                    self.epsilon(start, end)
                    continue
                entry = self.state(BasicState, rule)
                self.epsilon(start, entry)
                self.expression(child, entry, end, rule)
            self.atn.defineDecisionState(start)
        elif kind in ('*', '*?'):
            entry = self.state(StarLoopEntryState, rule)
            start, end = self.block(StarBlockStartState, rule)
            back = self.state(StarLoopbackState, rule)
            exit = self.state(LoopEndState, rule)
            entry.loopBackState = back
            exit.loopBackState = back
            self.epsilon(source, entry)
            self.epsilon(entry, start)
            self.epsilon(entry, exit)
            if kind == '*?':
                entry.transitions.reverse()
                entry.nonGreedy = True
            body = self.state(BasicState, rule)
            self.epsilon(start, body)
            self.expression(value, body, end, rule)
            self.epsilon(end, back)
            self.epsilon(back, entry)
            self.epsilon(exit, target)
            self.atn.defineDecisionState(entry)
        elif kind in ('+', '+?'):
            start, end = self.block(PlusBlockStartState, rule)
            back = self.state(PlusLoopbackState, rule)
            exit = self.state(LoopEndState, rule)
            start.loopBackState = back
            exit.loopBackState = back
            self.epsilon(source, start)
            body = self.state(BasicState, rule)
            self.epsilon(start, body)
            self.expression(value, body, end, rule)
            self.epsilon(end, back)
            self.epsilon(back, start)
            self.epsilon(back, exit)
            if kind == '+?':
                back.transitions.reverse()
                back.nonGreedy = True
            self.epsilon(exit, target)
            self.atn.defineDecisionState(back)
        else:
            raise ValueError(f'Unsupported ATN expression: {kind}')

    def lexer_action(self, command, argument):
        if command == 'skip':
            return LexerSkipAction.INSTANCE
        if command == 'more':
            return LexerMoreAction.INSTANCE
        if command == 'popMode':
            return LexerPopModeAction.INSTANCE
        if command in ('mode', 'pushMode'):
            cls = LexerModeAction if command == 'mode' else LexerPushModeAction
            return cls(int(argument) if argument.isdigit() else self.grammar.modes.index(argument))
        if command == 'type':
            return LexerTypeAction(int(argument) if argument.isdigit() else self.grammar.tokens[argument])
        if command == 'channel':
            return LexerChannelAction(int(argument) if argument.isdigit() else self.grammar.channels[argument])
        raise ValueError(f'Unsupported lexer command: {command}')


def build_atns(grammar, annotations=None):
    """Return verified lexer and parser ATNs for a validated grammar."""
    return ((ATNBuilder(grammar, lexer=True).build() if grammar.kind != 'parser' else None),
            (ATNBuilder(grammar, annotations=annotations).build() if grammar.rules else None))


def decision_lookahead(atn, annotations):
    """Use the same disjoint, predicate-free lookahead as ANTLR's LL(1) code."""
    analyzer, result = LL1Analyzer(atn), {}
    for state in atn.decisionToState:
        if len(state.transitions) < 2 or state.nonGreedy:
            continue
        alternatives, seen = [], set()
        for edge in state.transitions:
            look = IntervalSet()
            # The runtime's public getDecisionLookahead implementation has a
            # list allocation bug; its native LOOK traversal is fully usable.
            analyzer._LOOK(edge.target, None, PredictionContext.EMPTY, look,
                           set(), set(), False, False)
            tokens = set(look)
            if not tokens or LL1Analyzer.HIT_PRED in tokens or seen & tokens:
                break
            alternatives.append(sorted(tokens))
            seen |= tokens
        else:
            fallback = next((data for kind, data in annotations.get(state.stateNumber, [])
                             if kind == 'optional'), 0)
            if isinstance(state, (StarLoopEntryState, PlusLoopbackState)):
                fallback = next((i+1 for i, edge in enumerate(state.transitions)
                                 if isinstance(edge.target, LoopEndState)), 0)
            result[state.stateNumber] = (alternatives, fallback)
    return result
