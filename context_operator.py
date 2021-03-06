# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Contextual Anomaly Detector — Open Source Edition
#
# Copyright © 2016 Mikhail Smirnov <smirmik@gmail.com>
# Copyright © 2016 Gregory Petrosyan <gregory.petrosyan@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
# -----------------------------------------------------------------------------

import collections
import recordclass


Half = recordclass.recordclass('Half', [
    'fact_to_semi_ctx',             # fact => semi ctx (which was created with it)
    'facts_hash_to_semi_ctx_id',    # facts hash => semi ctx ids (sequential integers)
    'semi_ctxs',                    # semi ctx id => semi ctx
    'crossed_semi_ctxs',            # subset of semi_ctxs with len(.facts) > 0
])

Ctx = recordclass.recordclass('Ctx', [
    'c0',
    'c1',
    'num_activations',
    'right_facts',
    'zerolevel',
])

SemiCtx = recordclass.recordclass('SemiCtx', [
    'facts',
    'init_nfacts',
    'rsemi_ctx_id_to_ctx_id',
])

ActiveCtx = collections.namedtuple('ActiveCtx', [
    'ctx_id',
    'ctx_num_activations',
])


def _prepare_crossed_semi_ctxs(half, facts):
    for semi_ctx in half.crossed_semi_ctxs:
        semi_ctx.facts = []

    for fact in facts:
        for semi_ctx in half.fact_to_semi_ctx.get(fact, []):
            semi_ctx.facts.append(fact)

    half.crossed_semi_ctxs = [semi_ctx for semi_ctx in half.semi_ctxs if semi_ctx.facts]


class ContextOperator(object):
    def __init__(self, max_lsemi_ctxs_len):
        self.max_lsemi_ctxs_len = max_lsemi_ctxs_len

        self.left = Half({}, {}, [], [])
        self.right = Half({}, {}, [], [])
        self.ctxs = []

        self.new_ctx_id = False

    def cross_ctxs_right(self, facts, pot_new_zero_level_ctx):
        _prepare_crossed_semi_ctxs(self.right, facts)

        num_new_ctxs = self._add_ctxs_by_facts(pot_new_zero_level_ctx, zerolevel=True)
        active_ctxs = []
        num_selected_ctx = 0
        potential_new_ctxs = []

        for lsemi_ctx in self.left.crossed_semi_ctxs:
            for rsemi_ctx_id, ctx_id in lsemi_ctx.rsemi_ctx_id_to_ctx_id.iteritems():

                if ctx_id != self.new_ctx_id:
                    ctx = self.ctxs[ctx_id]
                    rsemi_ctx = self.right.semi_ctxs[rsemi_ctx_id]

                    if len(lsemi_ctx.facts) == lsemi_ctx.init_nfacts:
                        num_selected_ctx += 1
                        ctx.c0 += rsemi_ctx.init_nfacts
                        ctx.c1 += len(rsemi_ctx.facts)

                        if len(rsemi_ctx.facts) == rsemi_ctx.init_nfacts:
                            ctx.num_activations += 1
                            active_ctxs.append(ActiveCtx(ctx_id, ctx.num_activations))

                        elif ctx.zerolevel and num_new_ctxs and rsemi_ctx.facts and len(lsemi_ctx.facts) <= self.max_lsemi_ctxs_len:
                            potential_new_ctxs.append((tuple(lsemi_ctx.facts), tuple(rsemi_ctx.facts)))

                    elif ctx.zerolevel and num_new_ctxs and rsemi_ctx.facts and len(lsemi_ctx.facts) <= self.max_lsemi_ctxs_len:
                        potential_new_ctxs.append((tuple(lsemi_ctx.facts), tuple(rsemi_ctx.facts)))

        self.new_ctx_id = False

        return active_ctxs, num_selected_ctx, potential_new_ctxs, num_new_ctxs

    def cross_ctxs_left(self, facts, potential_new_ctxs):
        _prepare_crossed_semi_ctxs(self.left, facts)

        num_new_ctxs = self._add_ctxs_by_facts(potential_new_ctxs, zerolevel=False)
        max_pred_weight = 0.0
        prediction_ctxs = []

        for lsemi_ctx in self.left.semi_ctxs:
            if 0 < len(lsemi_ctx.facts) == lsemi_ctx.init_nfacts:
                for ctx_id in lsemi_ctx.rsemi_ctx_id_to_ctx_id.itervalues():
                    ctx = self.ctxs[ctx_id]

                    curr_pred_weight = ctx.c1 / float(ctx.c0) if ctx.c0 > 0 else 0.0

                    if curr_pred_weight > max_pred_weight:
                        max_pred_weight = curr_pred_weight
                        prediction_ctxs = [ctx]

                    elif curr_pred_weight == max_pred_weight:
                        prediction_ctxs.append(ctx)

        new_predictions = set(fact for ctx in prediction_ctxs for fact in ctx.right_facts)

        return num_new_ctxs, new_predictions

    def _add_ctxs_by_facts(self, new_ctxs, zerolevel):
        num_added_ctxs = 0

        for left_facts, right_facts in new_ctxs:
            lsemi_ctx_id = self._add_semi_ctx_by_facts(self.left, left_facts)
            rsemi_ctx_id = self._add_semi_ctx_by_facts(self.right, right_facts)

            next_free_ctx_id_number = len(self.ctxs)
            ctx_id = self.left.semi_ctxs[lsemi_ctx_id].rsemi_ctx_id_to_ctx_id.setdefault(rsemi_ctx_id, next_free_ctx_id_number)

            if ctx_id == next_free_ctx_id_number:
                ctx = Ctx(0, 0, 0, right_facts, zerolevel)
                self.ctxs.append(ctx)
                num_added_ctxs += 1
                if zerolevel:
                    self.new_ctx_id = ctx_id
            else:
                ctx = self.ctxs[ctx_id]
                if zerolevel:
                    ctx.zerolevel = True

        return num_added_ctxs

    def _add_semi_ctx_by_facts(self, half, facts):
        next_semi_ctx_number = len(half.facts_hash_to_semi_ctx_id)
        semi_ctx_id = half.facts_hash_to_semi_ctx_id.setdefault(hash(facts), next_semi_ctx_number)
        if semi_ctx_id == next_semi_ctx_number:
            semi_ctx = SemiCtx([], len(facts), {} if half == self.left else None)
            half.semi_ctxs.append(semi_ctx)
            for fact in facts:
                semi_ctxs = half.fact_to_semi_ctx.setdefault(fact, [])
                semi_ctxs.append(semi_ctx)
        return semi_ctx_id
