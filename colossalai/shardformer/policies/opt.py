from transformers.models.opt.modeling_opt import (
    OPTAttention,
    OPTDecoder,
    OPTDecoderLayer,
    OPTForCausalLM,
    OPTForSequenceClassification,
)

from colossalai.shardformer.layer import Embedding1D, FusedLayerNorm, Linear1D_Col, Linear1D_Row

from .basepolicy import ModulePolicyDescription, Policy, SubModuleReplacementDescription


class OPTPolicy(Policy):

    def config_sanity_check(self):
        pass

    def preprocess(self):
        # reshape the embedding layer
        r"""
        Reshape the Embedding layer to make the embedding dimension divisible by world_size
        """
        vocab_size = self.model.config.vocab_size
        world_size = self.shard_config.tensor_parallel_size
        if vocab_size % world_size != 0:
            new_vocab_size = vocab_size + world_size - vocab_size % world_size
            self.model.resize_token_embeddings(new_vocab_size)
        return self.model

    def module_policy(self):
        base_policy = {
            OPTDecoder:
                ModulePolicyDescription(attribute_replacement={},
                                        param_replacement=[],
                                        sub_module_replacement=[
                                            SubModuleReplacementDescription(
                                                suffix="embed_tokens",
                                                target_module=Embedding1D,
                                            )
                                        ]),
            OPTDecoderLayer:
                ModulePolicyDescription(attribute_replacement={},
                                        param_replacement=[],
                                        sub_module_replacement=[
                                            SubModuleReplacementDescription(
                                                suffix="fc1",
                                                target_module=Linear1D_Col,
                                            ),
                                            SubModuleReplacementDescription(
                                                suffix="fc2",
                                                target_module=Linear1D_Row,
                                            )
                                        ]),
            OPTAttention:
                ModulePolicyDescription(attribute_replacement={
                    "embed_dim": self.model.config.hidden_size // self.shard_config.tensor_parallel_size,
                    "num_heads": self.model.config.num_attention_heads // self.shard_config.tensor_parallel_size
                },
                                        param_replacement=[],
                                        sub_module_replacement=[
                                            SubModuleReplacementDescription(
                                                suffix="q_proj",
                                                target_module=Linear1D_Col,
                                            ),
                                            SubModuleReplacementDescription(
                                                suffix="k_proj",
                                                target_module=Linear1D_Col,
                                            ),
                                            SubModuleReplacementDescription(
                                                suffix="v_proj",
                                                target_module=Linear1D_Col,
                                            ),
                                            SubModuleReplacementDescription(
                                                suffix="out_proj",
                                                target_module=Linear1D_Row,
                                            ),
                                        ]),
        }

        # optimization configuration
        if self.shard_config.enable_fused_normalization:
            base_policy[OPTDecoder].sub_module_replacement.append(
                SubModuleReplacementDescription(suffix="final_layer_norm",
                                                target_module=FusedLayerNorm,
                                                ignore_if_not_exist=True))
            base_policy[OPTDecoderLayer].sub_module_replacement.extend([
                SubModuleReplacementDescription(suffix="self_attn_layer_norm",
                                                target_module=FusedLayerNorm,
                                                ignore_if_not_exist=True),
                SubModuleReplacementDescription(suffix="final_layer_norm",
                                                target_module=FusedLayerNorm,
                                                ignore_if_not_exist=True)
            ])

        return base_policy

    def new_model_class(self):
        return None

    def postprocess(self):
        return self.model


class OPTModelPolicy(OPTPolicy):

    def __init__(self) -> None:
        super().__init__()


class OPTForCausalLMPolicy(OPTPolicy):

    def module_policy(self):
        policy = super().module_policy()
        new_item = {
            OPTForCausalLM:
                ModulePolicyDescription(attribute_replacement={},
                                        param_replacement=[],
                                        sub_module_replacement=[
                                            SubModuleReplacementDescription(suffix="lm_head",
                                                                            target_module=Linear1D_Col,
                                                                            kwargs=dict(gather_output=True))
                                        ])
        }

        policy.update(new_item)
        return policy


class OPTForSequenceClassificationPolicy(OPTPolicy):

    def __init__(self) -> None:
        super().__init__()


class OPTForQuestionAnsweringPolicy(OPTPolicy):

    def __init__(self) -> None:
        super().__init__()
