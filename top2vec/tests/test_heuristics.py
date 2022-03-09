import pytest
from top2vec.Top2Vec import Top2Vec
from top2vec.similarity import (
    describe_closest_items,
    find_closest_items,
    generate_similarity_matrix,
    generate_csr_similarity_matrix,
)
import gensim
from sklearn.datasets import fetch_20newsgroups
import numpy as np

# get 20 newsgroups data
newsgroups_train = fetch_20newsgroups(
    subset="all", remove=("headers", "footers", "quotes")
)
# newsgroups_documents = newsgroups_train.data[0:2000]
newsgroups_documents = newsgroups_train.data

# train top2vec model with doc_ids provided
doc_ids = [str(num) for num in range(0, len(newsgroups_documents))]
top2vec_docids = Top2Vec(
    documents=newsgroups_documents,
    document_ids=doc_ids,
    speed="fast-learn",
    workers=8,
    umap_args={"random_state": 1337},
)

# test USE with model embedding
# This only gives us 2 topics when given 2000 documents, which ain't great
top2vec_use_model_embedding = Top2Vec(
    documents=newsgroups_documents,
    embedding_model="universal-sentence-encoder",
    use_embedding_model_tokenizer=True,
    umap_args={"random_state": 1337},
)
# test USE-multilang
top2vec_use_multilang = Top2Vec(
    documents=newsgroups_documents,
    embedding_model="universal-sentence-encoder-multilingual",
    umap_args={"random_state": 1337},
)
top2vec_use = Top2Vec(
    documents=newsgroups_documents,
    embedding_model="universal-sentence-encoder",
    umap_args={"random_state": 1337},
)

models = [
    top2vec_docids,
    top2vec_use_model_embedding,
    top2vec_use_multilang,
    top2vec_use,
]


@pytest.mark.parametrize("top2vec_model", models)
def test_topic_descriptions(top2vec_model: Top2Vec):
    # Is topn respected?
    topn = 100
    topic_descriptions = describe_closest_items(
        top2vec_model.topic_vectors,
        top2vec_model.word_vectors,
        top2vec_model.vocab,
        topn=topn,
    )
    topic_lens = [len(words) for (words, scores) in topic_descriptions]
    for topic_len in topic_lens:
        assert topic_len <= topn

    topn = 1000
    topic_descriptions = describe_closest_items(
        top2vec_model.topic_vectors,
        top2vec_model.word_vectors,
        top2vec_model.vocab,
        topn=topn,
    )
    topic_lens = [len(words) for (words, scores) in topic_descriptions]
    for topic_len in topic_lens:
        assert topic_len <= topn


@pytest.mark.parametrize("top2vec_model", models)
def test_document_descriptions(top2vec_model: Top2Vec):
    # Make sure we don't run out of memory
    maxDocs = 50
    topn = 1000
    document_descriptions = describe_closest_items(
        top2vec_model.document_vectors[:50],
        top2vec_model.word_vectors,
        top2vec_model.vocab,
        topn=topn,
    )
    doc_lens = [len(words) for (words, scores) in document_descriptions]
    for doc_len in doc_lens:
        assert doc_len <= topn
    assert len(doc_lens) == min(len(top2vec_model.document_vectors), maxDocs)
    percent_contained_per_doc = []
    for document_index in range(len(document_descriptions)):
        tokenized_doc = gensim.utils.simple_tokenize(
            newsgroups_documents[document_index]
        )
        lower_tokens = set([word.lower() for word in tokenized_doc])
        contained = [
            token
            for token in lower_tokens
            if token in document_descriptions[document_index][0]
        ]
        # So this is an interesting thing.
        # Not all documents will contain their closest word vectors
        percent_contained = len(contained) / len(lower_tokens)
        percent_contained_per_doc.append(percent_contained)
    average_percent_contained_per_doc = sum(percent_contained_per_doc) / len(
        percent_contained_per_doc
    )
    print(average_percent_contained_per_doc)
    assert average_percent_contained_per_doc > 0.125
    # TODO: Compare with the _herusitic version of the model


@pytest.mark.parametrize("top2vec_model", models)
def test_document_topic_composition(top2vec_model: Top2Vec):
    # Theory is that MOST documents should be composed of a single topic
    # However in this case our USE has almost 100 topics despite there
    # being only 20 newsgroups. Therefore there is some duplication
    topn = 100
    document_topics = find_closest_items(
        top2vec_model.document_vectors, top2vec_model.topic_vectors, topn=topn
    )
    # Another potential heuristic: look for the first major jump
    num_topics_per_doc = [len(scores) for indices, scores in document_topics]
    for num_topics in num_topics_per_doc:
        assert num_topics <= topn

    # Now let's see if the doc x topic matrix looks good
    docTopicMatrix = generate_similarity_matrix(
        top2vec_model.document_vectors, top2vec_model.topic_vectors, topn=topn
    )
    numZeroes = np.count_nonzero(docTopicMatrix == 0)
    sparsity = numZeroes / (docTopicMatrix.size)
    # Our sparsity should be high
    # It looks like we've got some weirdness where a few of the items
    # have a TON of topics
    assert sparsity > 0.55

    sparse_matrix = generate_csr_similarity_matrix(
        top2vec_model.document_vectors, top2vec_model.topic_vectors, topn=topn
    )
    assert sparse_matrix.size == np.count_nonzero(docTopicMatrix)
    # TODO: Is there other stuff I want to test here?
    # Running just document similarity and using the elbow-finding method
    # doesn't work THAT great
    # It at least has SOME cut-off, which is better than nothing


def test_USE_topic_descriptions():
    assert top2vec_use_model_embedding.get_num_topics() == 80
    topn = 1000
    topic_descriptions = describe_closest_items(
        top2vec_use_model_embedding.topic_vectors,
        top2vec_use_model_embedding.word_vectors,
        top2vec_use_model_embedding.vocab,
        topn=topn,
    )
    topic_lens = [len(words) for (words, scores) in topic_descriptions]

    # Let's find our space topic
    space_topic = None

    for topic_len in topic_lens:
        assert topic_len <= topn

    for words, scores in topic_descriptions:
        if "spacecraft" in words[:10]:
            space_topic = words
            break
    assert space_topic is not None
    assert "jpl" in space_topic[:10]
    assert "orbiter" in space_topic[:10]
    assert "satellites" in space_topic[:10]
    assert "astronaut" in space_topic[:10]
    assert len(words) > 100
